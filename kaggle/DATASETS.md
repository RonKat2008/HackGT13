# Datasets

Two public Kaggle datasets. The abstracts set trains the probe. The tabular set is the one a demo claim may rerun.

## Abstracts

- slug: heleneeriksen/gpt-vs-human-a-corpus-of-research-abstracts
- url: https://www.kaggle.com/datasets/heleneeriksen/gpt-vs-human-a-corpus-of-research-abstracts
- file: `kaggle/downloads/data_set.csv`
- label columns: `ai_generated`, `is_ai_generated`
- download: `kaggle datasets download -d heleneeriksen/gpt-vs-human-a-corpus-of-research-abstracts -p kaggle/downloads --unzip`

`kaggle datasets list -s "gpt vs human a corpus of research abstracts"` returned this slug. The unzipped CSV header is `title,abstract,ai_generated,is_ai_generated`. The CLI reported license `other`.

## Tabular

- slug: yasserh/titanic-dataset
- url: https://www.kaggle.com/datasets/yasserh/titanic-dataset
- file: `Titanic-Dataset.csv` (about 22 KB zipped, one CSV)
- target column: `Survived`
- license: CC0-1.0
- download: `kaggle datasets download -d yasserh/titanic-dataset -p kaggle/downloads --unzip`

`kaggle datasets list -s "tabular classification"` returned this slug among the small sets. The card subtitle is "Titanic Survival Prediction Dataset" and the objective is to predict whether the passenger survives. The CSV header is `PassengerId,Survived,Pclass,Name,Sex,Age,SibSp,Parch,Ticket,Fare,Cabin,Embarked`, so the documented target is `Survived`.
