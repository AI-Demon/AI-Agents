from __future__ import annotations

from enum import Enum
from typing import Annotated, Self, Union

import pytest
from google.genai.types import FunctionDeclaration, Schema, Type
from pydantic import BaseModel, Field

from src.agents._gemini.utils import _generate_schema_from_python_type, func_to_gemi


class TestEnum(Enum):
    """Тестовый enum для тестирования."""

    VALUE_A = "a"
    VALUE_B = "b"
    VALUE_C = "c"


class TestModel(BaseModel):
    """Тестовая модель для тестирования."""

    name: str = Field(description="Name field")
    age: int = Field(description="Age field")
    email: str | None = Field(default=None, description="Optional email")


class NestedModel(BaseModel):
    """Вложенная модель для тестирования."""

    nested_field: str = Field(description="Nested field")
    test_model: TestModel = Field(description="Test model field")


class TestGenerateSchemaFromPythonType:
    """Тесты для функции _generate_schema_from_python_type."""

    def test_basic_types(self: Self) -> None:
        """Тест базовых типов Python."""
        assert _generate_schema_from_python_type(str) == Schema(type=Type.STRING)
        assert _generate_schema_from_python_type(int) == Schema(type=Type.INTEGER)
        assert _generate_schema_from_python_type(float) == Schema(type=Type.NUMBER)
        assert _generate_schema_from_python_type(bool) == Schema(type=Type.BOOLEAN)
        assert _generate_schema_from_python_type(dict) == Schema(type=Type.OBJECT)
        assert _generate_schema_from_python_type(type(None)) == Schema(type=Type.NULL)

    def test_field_info_description(self: Self) -> None:
        """Тест добавления описания из FieldInfo."""
        field_info = Field(description="Test description")
        schema = _generate_schema_from_python_type(str, field_info)
        assert schema.description == "Test description"
        assert schema.type == Type.STRING

    def test_optional_type(self: Self) -> None:
        """Тест Optional типов (Union с None)."""  # noqa: RUF002
        optional_str = str | None
        schema = _generate_schema_from_python_type(optional_str)
        assert schema.type == Type.STRING

        # Тест с FieldInfo  # noqa: RUF003
        field_info = Field(description="Optional string")
        schema = _generate_schema_from_python_type(optional_str, field_info)
        assert schema.type == Type.STRING
        assert schema.description == "Optional string"

    def test_enum_type(self: Self) -> None:
        """Тест для Enum типов."""
        schema = _generate_schema_from_python_type(TestEnum)
        assert schema.type == Type.STRING
        assert schema.enum == ["a", "b", "c"]

    def test_enum_with_description(self: Self) -> None:
        """Тест для Enum с описанием."""  # noqa: RUF002
        field_info = Field(description="Test enum field")
        schema = _generate_schema_from_python_type(TestEnum, field_info)
        assert schema.type == Type.STRING
        assert schema.enum == ["a", "b", "c"]
        assert schema.description == "Test enum field"

    def test_list_type(self: Self) -> None:
        """Тест для типа list."""
        schema = _generate_schema_from_python_type(list[str])
        assert schema.type == Type.ARRAY
        assert schema.items is not None
        assert schema.items.type == Type.STRING

    def test_list_with_complex_items(self: Self) -> None:
        """Тест для списка с сложными элементами."""  # noqa: RUF002
        schema = _generate_schema_from_python_type(list[TestModel])
        assert schema.type == Type.ARRAY
        assert schema.items is not None
        assert schema.items.type == Type.OBJECT
        assert schema.items is not None
        assert schema.items.properties is not None
        assert "name" in schema.items.properties
        assert "age" in schema.items.properties
        assert "email" in schema.items.properties

    def test_pydantic_model(self: Self) -> None:
        """Тест для Pydantic модели."""
        schema = _generate_schema_from_python_type(TestModel)
        assert schema.type == Type.OBJECT
        assert schema.properties is not None
        assert len(schema.properties) == 3  # noqa: PLR2004
        assert "name" in schema.properties
        assert "age" in schema.properties
        assert "email" in schema.properties
        assert schema.properties["name"].type == Type.STRING
        assert schema.properties["age"].type == Type.INTEGER
        assert schema.properties["email"].type == Type.STRING
        assert schema.required == ["name", "age"]  # email не обязательное

    def test_nested_pydantic_model(self: Self) -> None:
        """Тест для вложенных Pydantic моделей."""
        schema = _generate_schema_from_python_type(NestedModel)
        assert schema.type == Type.OBJECT
        assert schema.properties
        assert "nested_field" in schema.properties
        assert "test_model" in schema.properties
        assert schema.properties["test_model"].type == Type.OBJECT
        assert "name" in schema.properties["test_model"].properties  # type: ignore

    def test_unsupported_union_type(self: Self) -> None:
        """Тест для неподдерживаемых Union типов."""
        with pytest.raises(ValueError, match=r"Unsupported type 'typing.Union\[str, int\]'"):
            _generate_schema_from_python_type(Union[str, int])  # type: ignore[arg-type]  # noqa: UP007

    def test_list_without_type_args(self: Self) -> None:
        """Тест для list без указания типа элементов."""
        with pytest.raises(ValueError, match="List type must specify item type"):
            _generate_schema_from_python_type(list)

    def test_unsupported_type(self: Self) -> None:
        """Тест для неподдерживаемого типа."""
        with pytest.raises(ValueError, match="Unsupported type"):
            _generate_schema_from_python_type(complex)


class TestFuncToGemi:
    """Тесты для функции func_to_gemi."""

    def test_simple_function(self: Self) -> None:
        """Тест простой функции."""

        def test_func(
            x: Annotated[int, Field(description="Integer parameter")],
            y: Annotated[str, Field(description="String parameter")],
        ) -> str:
            """Test function description."""
            return f"{x}: {y}"

        result = func_to_gemi(test_func)

        assert isinstance(result, FunctionDeclaration)
        assert result.name == "test_func"
        assert result.description == "Test function description."
        assert result.parameters is not None
        assert result.parameters.type == Type.OBJECT
        assert result.parameters.properties is not None
        assert len(result.parameters.properties) == 2  # noqa: PLR2004
        assert "x" in result.parameters.properties
        assert "y" in result.parameters.properties
        assert result.parameters.properties["x"].type == Type.INTEGER
        assert result.parameters.properties["y"].type == Type.STRING
        assert result.parameters.required == ["x", "y"]

    def test_function_with_optional_params(self: Self) -> None:
        """Тест функции с опциональными параметрами."""  # noqa: RUF002

        def test_func(
            required_param: Annotated[str, Field(description="Required parameter")],
            optional_param: Annotated[  # noqa: ARG001
                int | None,
                Field(default=None, description="Optional parameter"),
            ],
        ) -> str:
            """Function with optional parameters."""
            return str(required_param)

        result = func_to_gemi(test_func)

        assert result.parameters is not None
        assert result.parameters.properties is not None
        assert len(result.parameters.properties) == 2  # noqa: PLR2004
        assert result.parameters.required == ["required_param"]
        assert "optional_param" in result.parameters.properties
        assert result.parameters.properties["optional_param"].type == Type.INTEGER

    def test_function_with_enum_param(self: Self) -> None:
        """Тест функции с enum параметром."""  # noqa: RUF002

        def test_func(enum_param: Annotated[TestEnum, Field(description="Enum parameter")]) -> str:
            """Function with enum parameter."""
            return enum_param.value

        result = func_to_gemi(test_func)

        assert result.parameters is not None
        assert result.parameters.properties is not None
        assert result.parameters.properties["enum_param"].type == Type.STRING
        assert result.parameters.properties["enum_param"].enum == ["a", "b", "c"]

    def test_function_with_list_param(self: Self) -> None:
        """Тест функции с параметром-списком."""  # noqa: RUF002

        def test_func(list_param: Annotated[list[str], Field(description="List parameter")]) -> str:
            """Function with list parameter."""
            return str(list_param)

        result = func_to_gemi(test_func)

        assert result.parameters is not None
        assert result.parameters.properties is not None
        assert result.parameters.properties["list_param"].type == Type.ARRAY
        assert result.parameters.properties["list_param"].items is not None
        assert result.parameters.properties["list_param"].items.type == Type.STRING

    def test_function_with_model_param(self: Self) -> None:
        """Тест функции с параметром-моделью."""  # noqa: RUF002

        def test_func(model_param: Annotated[TestModel, Field(description="Model parameter")]) -> str:
            """Function with model parameter."""
            return model_param.name

        result = func_to_gemi(test_func)

        assert result.parameters is not None
        assert result.parameters.properties is not None
        assert result.parameters.properties["model_param"].type == Type.OBJECT
        assert isinstance(result.parameters.properties["model_param"], Schema)
        assert "name" in result.parameters.properties["model_param"].properties  # type: ignore
        assert "age" in result.parameters.properties["model_param"].properties  # type: ignore

    def test_function_without_docstring(self: Self) -> None:
        """Тест функции без docstring."""

        def test_func(x: Annotated[int, Field(description="Integer parameter")]) -> str:
            return str(x)

        with pytest.raises(ValueError, match="must have a docstring description"):
            func_to_gemi(test_func)

    def test_function_with_non_annotated_param(self: Self) -> None:
        """Тест функции с неаннотированным параметром."""  # noqa: RUF002

        def test_func(x: int) -> str:
            """Function with non-annotated parameter."""
            return str(x)

        with pytest.raises(ValueError, match="Only Annotated is supported for parameters"):
            func_to_gemi(test_func)

    def test_function_with_field_without_description(self: Self) -> None:
        """Тест функции с Field без описания."""  # noqa: RUF002

        def test_func(x: Annotated[int, Field()]) -> str:
            """Function with field without description."""
            return str(x)

        with pytest.raises(ValueError, match="has no description in its Field"):
            func_to_gemi(test_func)

    def test_complex_function(self: Self) -> None:
        """Тест сложной функции с различными типами параметров."""  # noqa: RUF002

        def complex_func(  # noqa: PLR0913
            name: Annotated[str, Field(description="User name")],
            age: Annotated[int, Field(description="User age")],
            email: Annotated[str | None, Field(default=None, description="Optional email")],  # noqa: ARG001
            tags: Annotated[list[str], Field(description="User tags")],  # noqa: ARG001
            status: Annotated[TestEnum, Field(description="User status")],  # noqa: ARG001
            profile: Annotated[TestModel, Field(description="User profile")],  # noqa: ARG001
        ) -> dict:
            """Complex function with various parameter types."""
            return {"name": name, "age": age}

        result = func_to_gemi(complex_func)

        assert result.parameters is not None
        assert result.parameters.properties is not None
        assert len(result.parameters.properties) == 6  # noqa: PLR2004
        assert result.parameters.required == ["name", "age", "tags", "status", "profile"]

        # Проверяем типы всех параметров
        props = result.parameters.properties
        assert props["name"].type == Type.STRING
        assert props["age"].type == Type.INTEGER
        assert props["email"].type == Type.STRING
        assert props["tags"].type == Type.ARRAY
        assert props["tags"].items is not None
        assert props["tags"].items.type == Type.STRING
        assert props["status"].type == Type.STRING
        assert props["status"].enum == ["a", "b", "c"]
        assert props["profile"].type == Type.OBJECT
        assert isinstance(props["profile"], Schema)
        assert "name" in props["profile"].properties  # type: ignore

    def test_function_with_fine_tunes(self: Self) -> None:
        """Тест функции с параметром fine_tunes (должен игнорироваться)."""  # noqa: RUF002

        def test_func(x: Annotated[int, Field(description="Integer parameter")]) -> str:
            """Test function."""
            return str(x)

        result = func_to_gemi(test_func, fine_tunes={"some": "value"})

        # fine_tunes должен игнорироваться без ошибок
        assert isinstance(result, FunctionDeclaration)
        assert result.name == "test_func"


class TestEdgeCases:
    """Тесты для edge cases."""

    def test_function_with_return_annotation(self: Self) -> None:
        """Тест функции с аннотацией возвращаемого значения."""  # noqa: RUF002

        def test_func(
            x: Annotated[int, Field(description="Integer parameter")],
        ) -> Annotated[str, Field(description="Return value")]:
            """Test function with return annotation."""
            return str(x)

        # Функция должна работать, но return аннотация игнорируется
        result = func_to_gemi(test_func)
        assert isinstance(result, FunctionDeclaration)
        assert result.parameters is not None
        assert result.parameters.properties is not None
        assert len(result.parameters.properties) == 1

    def test_empty_function(self: Self) -> None:
        """Тест функции без параметров."""

        def empty_func() -> str:
            """Empty function."""
            return "empty"

        result = func_to_gemi(empty_func)
        assert result.parameters
        assert result.parameters.properties is not None
        assert len(result.parameters.properties) == 0
        assert result.parameters.required == []

    def test_function_with_multiline_docstring(self: Self) -> None:
        """Тест функции с многострочным docstring."""  # noqa: RUF002

        def test_func(x: Annotated[int, Field(description="Integer parameter")]) -> str:
            """This is a multiline docstring
            with multiple lines of description
            .
            """  # noqa: D205, D404
            return str(x)

        result = func_to_gemi(test_func)
        assert "multiline docstring" in result.description  # type: ignore
        assert "multiple lines" in result.description  # type: ignore
