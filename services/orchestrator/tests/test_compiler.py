import compiler
from dsl import Operation, Spec

TITANIC = "We evaluate on the Titanic passenger dataset (Kaggle, yasserh/titanic-dataset)."
SURVIVED = "Of the 891 passengers, 342 survived."
FIRST_CLASS = "317 passengers travelled in first class."


def test_titanic_sentences_compile() -> None:
    mention = compiler.compile_claim(TITANIC, ask=lambda _text: None)
    assert mention == []
    assert compiler.dataset_slug(TITANIC) == "yasserh/titanic-dataset"

    survived = compiler.compile_claim(SURVIVED, ask=lambda _text: (_ for _ in ()).throw(AssertionError("model")))
    assert survived == [
        Spec(operation=Operation.ROWS, expected=891),
        Spec(operation=Operation.COUNT_EQ, column="Survived", equals=1, expected=342),
    ]

    first = compiler.compile_claim(FIRST_CLASS, ask=lambda _text: (_ for _ in ()).throw(AssertionError("model")))
    assert first == [Spec(operation=Operation.COUNT_EQ, column="Pclass", equals=1, expected=317)]


def test_rows_and_mean_patterns() -> None:
    rows = compiler.compile_claim("The table contains 891 passengers.", ask=lambda _text: None)
    assert rows == [Spec(operation=Operation.ROWS, expected=891)]
    mean = compiler.compile_claim("The mean Age of 29.7 is reported.", ask=lambda _text: None)
    assert mean == [Spec(operation=Operation.MEAN, column="Age", expected=29.7)]


def test_model_json_is_validated() -> None:
    spec = compiler.compile_claim(
        "Median fare was about thirty two.",
        ask=lambda _text: '{"operation":"MEDIAN","column":"Fare","expected":32.2}',
    )
    assert spec == [Spec(operation=Operation.MEDIAN, column="Fare", expected=32.2)]


def test_model_text_that_is_not_a_spec_is_rejected() -> None:
    assert compiler.compile_claim("Some claim.", ask=lambda _text: "import pandas\npandas.read_csv('x')") == []
    assert (
        compiler.compile_claim(
            "Some claim.",
            ask=lambda _text: '{"operation":"COUNT_EQ","column":"Survived","code":"print(1)"}',
        )
        == []
    )
