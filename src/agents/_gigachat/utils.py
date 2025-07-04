from __future__ import annotations

from enum import Enum
from types import NoneType, UnionType
from typing import TYPE_CHECKING, Annotated, Any, get_args, get_origin, get_type_hints

import pandas as pd
import pdfplumber
from gigachat.models import Function, FunctionParameters
from gigachat.models.function_parameters_property import FunctionParametersProperty
from pydantic import BaseModel

# from gigachat.models.few_shot_example import FewShotExample
from pydantic.fields import FieldInfo

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

TYPES_MAP = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
    list: "array",
    dict: "object",
}


def _generate_giga_param_property(
    py_type: type | UnionType,
    field_info: FieldInfo | None = None,
) -> FunctionParametersProperty:
    """Рекурсивно генерирует объект FunctionParametersProperty для GigaChat API."""
    origin_type = get_origin(py_type) or py_type
    args_type = get_args(py_type)

    property_description = field_info.description if field_info else ""
    enum_values = None
    items_schema = None
    properties_schema = None
    required_properties = None

    if origin_type is UnionType:
        if len(args_type) == 2 and NoneType in args_type:  # noqa: PLR2004
            actual_type = next(t for t in args_type if t is not NoneType)
            return _generate_giga_param_property(actual_type, field_info)
        msg = f"Only Union with None is supported in GigaChat schema generation. Got: {py_type}"
        raise ValueError(msg)

    if isinstance(origin_type, type) and issubclass(origin_type, Enum):
        schema_type = "string"
        enum_values = [e.value for e in origin_type]
        return FunctionParametersProperty(type=schema_type, description=property_description, enum=enum_values)  # type: ignore[call-arg]

    if origin_type is list:
        if not args_type:
            msg = f"List type must specify item type (e.g., list[str]). Got: {py_type}"
            raise ValueError(msg)

        items_schema = _generate_giga_param_property(args_type[0])

        return FunctionParametersProperty(type="array", description=property_description, items=items_schema)  # type: ignore[call-arg]

    # Handle Pydantic BaseModel (OBJECT) types
    if isinstance(origin_type, type) and issubclass(origin_type, BaseModel):
        properties_schema = {}
        required_properties = []
        for field_name, model_field in origin_type.model_fields.items():  # type: ignore[attr-defined]
            # Извлекаем FieldInfo из Pydantic ModelField для рекурсии
            nested_field_info = FieldInfo(description=model_field.description)
            properties_schema[field_name] = _generate_giga_param_property(model_field.annotation, nested_field_info)  # type: ignore[call-arg]
            if model_field.is_required():
                required_properties.append(field_name)

        return FunctionParametersProperty(
            type="object",
            description=property_description,
            properties=properties_schema,
            required=required_properties,  # type: ignore[call-arg]
        )

    schema_type = TYPES_MAP.get(origin_type)  # type: ignore[assignment, arg-type]
    if schema_type:
        return FunctionParametersProperty(type=schema_type, description=property_description)  # type: ignore[call-arg]

    msg = f"Unsupported type '{py_type}' in GigaChat schema generation."
    raise ValueError(msg)


def func_to_giga(
    func: Callable,
    # examples: list[dict[Literal["request", "params"], str | dict[str, Any]]] | None = None,
    fine_tunes: dict[str, Any] | None = None,
) -> Function:
    """Создать описание функции для модели GigaChat.

    Пример создания функции:
    ```python
    def foo(
        x: Annotated[int, Field(description="some int")],
        y: Annotated[int | None, Field(default=None, description="Not req int")],
    ) -> tuple[str, int]:
        '''Some desc'''
        return "err", 7


    tool = func_to_giga(foo)
    ```
    """
    props: dict[str, FunctionParametersProperty] = {}
    required: list[str] = []

    func_doc = func.__doc__
    if not func_doc:
        msg = f"Function '{func.__name__}' must have a docstring description."
        raise ValueError(msg)

    for p, ann in get_type_hints(func, include_extras=True).items():
        if p == "return":
            continue

        if get_origin(ann) is not Annotated:
            msg = (
                f"Only Annotated is supported for parameters. "
                f"Check your function {func.__name__}. Parameter: '{p}', Got: {ann}"
            )
            raise ValueError(
                msg,
            )

        py_type: type | UnionType = get_args(ann)[0]
        field_info: FieldInfo = get_args(ann)[1]

        if not field_info.description:
            msg = f"Field '{p}' has no description in its Field()."
            raise ValueError(msg)

        param_property = _generate_giga_param_property(py_type, field_info)
        props[p] = param_property

        if field_info.is_required():
            required.append(p)

    # few_shot_examples_list: list[FewShotExample] | None = None
    # if examples:
    #     # Убедитесь, что FewShotExample импортирован, если вы его используете  # noqa: RUF003
    #     from gigachat.models.few_shot_example import FewShotExample
    #     few_shot_examples_list = [FewShotExample(**example) for example in examples]

    giga_func = Function(
        name=func.__name__,
        description=func_doc,
        parameters=FunctionParameters(properties=props, required=required),
        # few_shot_examples=few_shot_examples_list,
    )
    if not fine_tunes:
        return giga_func

    return Function(**(giga_func.dict() | fine_tunes))


def pdf_to_dict(pdf_path: Path | str) -> dict[str, Any]:
    """Извлечение структурированных данных из PDF."""
    result: dict[str, dict[str, Any] | list[Any]] = {
        "pages": [],
        "tables": [],
        "metadata": {},
    }

    with pdfplumber.open(pdf_path) as pdf:
        result["metadata"] = pdf.metadata
        for i, page in enumerate(pdf.pages):
            page_data = {
                "page_number": i + 1,
                "text": page.extract_text(),
                "tables": [],
                "images": len(page.images),
            }
            # Извлечение таблиц
            tables = page.extract_tables()
            for j, table in enumerate(tables):
                if table:
                    df = pd.DataFrame(table[1:], columns=table[0])  # noqa: PD901
                    table_dict = {
                        "table_id": j + 1,
                        "data": df.to_dict("records"),
                        "columns": list(df.columns),
                    }
                    page_data["tables"].append(table_dict)
                    result["tables"].append(table_dict)  # type: ignore[union-attr]

            result["pages"].append(page_data)  # type: ignore[union-attr]

    return result
