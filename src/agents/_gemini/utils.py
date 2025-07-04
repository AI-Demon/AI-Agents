from __future__ import annotations

from enum import Enum
from types import NoneType, UnionType
from typing import TYPE_CHECKING, Annotated, Any, get_args, get_origin, get_type_hints

from google.genai.types import FunctionDeclaration, Schema, Type
from pydantic import BaseModel
from pydantic.fields import FieldInfo

if TYPE_CHECKING:
    from collections.abc import Callable

TYPES_MAP = {
    NoneType: Type.NULL,
    str: Type.STRING,
    int: Type.INTEGER,
    float: Type.NUMBER,
    bool: Type.BOOLEAN,
    list: Type.ARRAY,
    dict: Type.OBJECT,
}


def _generate_schema_from_python_type(
    py_type: type | UnionType,
    field_info: FieldInfo | None = None,  # FieldInfo может содержать описание и другую инфо
) -> Schema:
    """Рекурсивно генерирует объект Schema для типа Python, включая вложенные типы."""
    origin_type = get_origin(py_type) or py_type
    args_type = get_args(py_type)
    schema_description = field_info.description if field_info else None
    enum_values = None

    # TODO: Можно усложнить поддержкой многих типов, например, Union[List[str], Set[int]],  # noqa: FIX002, TD002, TD003
    # но лучше продумывать сигнатуру функций
    if origin_type is UnionType:
        if len(args_type) == 2 and NoneType in args_type:  # noqa: PLR2004
            actual_type = next(t for t in args_type if t is not NoneType)
            return _generate_schema_from_python_type(actual_type, field_info)
        msg = f"Only Union with None is supported in schema generation. Got: {py_type}"
        raise ValueError(msg)

    if isinstance(origin_type, type) and issubclass(origin_type, Enum):
        schema_type = Type.STRING
        enum_values = [e.value for e in origin_type]
        return Schema(type=schema_type, description=schema_description, enum=enum_values)

    if origin_type is list:
        if not args_type:
            msg = f"List type must specify item type (e.g., list[str]). Got: {py_type}"
            raise ValueError(msg)

        item_schema = _generate_schema_from_python_type(args_type[0])

        return Schema(type=Type.ARRAY, description=schema_description, items=item_schema)

    # Это более сложный случай, требует рекурсивного парсинга полей BaseModel
    if isinstance(origin_type, type) and issubclass(origin_type, BaseModel):
        properties = {}
        required_props = []
        for field_name, model_field in origin_type.model_fields.items():  # type: ignore[attr-defined]
            # Извлекаем FieldInfo из Pydantic ModelField, если она есть
            # Pydantic 2.0+ хранит это в model_field.json_schema_extra.field_info
            # или можно попробовать напрямую создать FieldInfo, но это не идеально
            nested_field_info = FieldInfo(description=model_field.description)  # Создаем FieldInfo для рекурсии
            properties[field_name] = _generate_schema_from_python_type(model_field.annotation, nested_field_info)  # type: ignore[assignment]
            if model_field.is_required():
                required_props.append(field_name)

        return Schema(type=Type.OBJECT, description=schema_description, properties=properties, required=required_props)

    if origin_type in TYPES_MAP:
        return Schema(type=TYPES_MAP[origin_type], description=schema_description)

    msg = f"Unsupported type '{py_type}'"
    raise ValueError(msg)


def func_to_gemi(
    func: Callable,
    fine_tunes: dict[str, Any] | None = None,  # noqa: ARG001
) -> FunctionDeclaration:
    """Создать описание функции для модели `Gemini`.

    Пример создания функции:
    ```python
    def foo(
        x: Annotated[int, Field(description="some int")],
        y: Annotated[int | None, Field(default=None, description="Not req int")],
    ) -> tuple[str, int]:
        '''Some desc'''
        return "err", 7


    tool = func_to_gemi(foo)
    ```

    TODO: Добавить описание возвращаемого значенияю
    """
    props: dict[str, Schema] = {}
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
            raise ValueError(msg)

        py_type: type | UnionType = get_args(ann)[0]
        field_info: FieldInfo = get_args(ann)[1]  # Это будет объект FieldInfo из pydantic

        if not field_info.description:
            msg = f"Field '{p}' has no description in its Field()."
            raise ValueError(msg)

        param_schema = _generate_schema_from_python_type(py_type, field_info)
        if field_info.description:
            param_schema.description = field_info.description

        props[p] = param_schema
        if field_info.is_required():
            required.append(p)

    return FunctionDeclaration(
        name=func.__name__,
        description=func_doc,
        parameters=Schema(type=Type.OBJECT, properties=props, required=required),
    )
