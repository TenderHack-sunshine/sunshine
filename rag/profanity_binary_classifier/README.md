# Binary Russian Profanity Classifier

Изолированный ML-проект внутри `rag/` для бинарной классификации русскоязычных обращений в поддержку по наличию узнаваемой нецензурной лексемы.

Исходный файл читается только на входе: `../data/profanity_binary.xlsx`. Скрипты не создают случайное разбиение и используют только колонку `split`.

## Структура

```text
profanity_binary_classifier/
  configs/default.json
  requirements.txt
  validate_data.py
  train.py
  evaluate.py
  run_experiment.py
  predict.py
  src/profanity_ml/
  tests/
```

`artifacts/` создается при запуске и содержит модель, threshold, логи, метрики, таблицы сравнения и CSV с false positives / false negatives.

## Установка

```bash
cd rag/profanity_binary_classifier
python -m pip install -r requirements.txt
```

На этой Windows-машине может понадобиться `py` вместо `python`.

## Проверка данных

```bash
python validate_data.py
```

Проверяется:

- отсутствие пустых `text`;
- только `label` 0 и 1;
- отсутствие одинаковых `text`;
- отсутствие пересечения `group_id` между split;
- отсутствие дубликатов `text` между split;
- равномерность классов;
- количество строк в каждом split.

## Полный эксперимент

```bash
python run_experiment.py
```

Скрипт:

- считает rule-based baseline;
- считает `cointegrated/rubert-tiny-toxicity`, используя вероятность `obscenity`, если такая голова/метка есть в конфиге модели;
- дообучает `cointegrated/rubert-tiny2`;
- сохраняет лучшую модель по validation PR-AUC;
- выбирает threshold только на validation: максимум Precision при Recall класса 1 >= 0.95;
- один раз оценивает test с зафиксированным threshold;
- сохраняет `artifacts/experiment_report.json` и `artifacts/comparison_table_test.csv`.

Если модель уже обучена:

```bash
python run_experiment.py --skip-training
```

Если нет доступа к Hugging Face для готового baseline:

```bash
python run_experiment.py --skip-toxicity
```

## Отдельные команды

Fine-tuning:

```bash
python train.py
```

Оценка одного метода:

```bash
python evaluate.py --system rule --split test
python evaluate.py --system toxicity --split test
python evaluate.py --system finetuned --split test
```

CLI-предсказание:

```bash
python predict.py --text "текст обращения"
```

Формат вывода:

```json
{
  "text": "текст обращения",
  "label": 0,
  "probability": 0.12,
  "threshold": 0.64
}
```

## Параметры основной модели

- `seed=42`
- `max_length=256`
- `stride=64`
- `learning_rate=2e-5`
- `batch_size=32` на CUDA
- `batch_size=8` на CPU
- `epochs=5`, минимум 3 эпохи перед early stopping
- `weight_decay=0.01`
- `early_stopping_patience=2`
- `AutoModelForSequenceClassification(num_labels=2)`

Для длинных обращений inference выполняется sliding-window: окна по `max_length=256`, `stride=64`, итоговая вероятность равна максимуму по окнам.

## Метрики

Для validation и test считаются:

- Precision, Recall, F1 класса 1;
- Macro-F1;
- PR-AUC;
- ROC-AUC;
- confusion matrix;
- False Positive Rate;
- False Negative Rate;
- false positives на 1000 чистых сообщений;
- Recall по `example_type`;
- Recall по `transformation`;
- Recall на замаскированных примерах.

Accuracy намеренно не используется как основная метрика.

## Анализ ошибок

Для каждого метода сохраняются минимум до 20 наиболее уверенных false positive и 20 false negative примеров:

```text
artifacts/<system>/validation_false_positives_top20.csv
artifacts/<system>/validation_false_negatives_top20.csv
artifacts/<system>/test_false_positives_top20.csv
artifacts/<system>/test_false_negatives_top20.csv
```

Разметка test на основании предсказаний не изменяется.

## Ограничения синтетического датасета

- Сбалансированные классы в каждом split не отражают реальную частоту мата в поддержке.
- Синтетические маскировки могут быть уже и чище реального пользовательского шума.
- Повторы вариантов одной фразы через `group_id` снижают риск leakage, но не заменяют проверку на живом потоке.
- Метрики на test показывают качество на заданной генеративной схеме данных, а не гарантируют production-rate FP/FN.
