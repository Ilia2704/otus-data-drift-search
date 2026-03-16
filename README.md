# Упрощенное решение для Data Drift Detection

Упрощенное решение на Kubernetes без использования Bitnami Helm charts. Использует простые манифесты и локальное хранилище.

## Архитектура

- **Drifter** - FastAPI сервис, генерирующий данные с возможным дрифтом
- **PostgreSQL** - база данных для метаданных Airflow
- **MinIO** - S3-совместимое хранилище для данных и артефактов
- **MLflow** - сервер для трекинга экспериментов (SQLite + MinIO для артефактов)
- **Airflow** - standalone режим для оркестрации проверок дрифта
- **Evidently** - библиотека для детекции дрифта данных

## Предварительные требования

- Minikube
- kubectl
- Docker

## Установка

### 1. Запуск Minikube кластера

```bash
# Запускаем Minikube с достаточными ресурсами
minikube start

# Проверяем, что кластер работает
kubectl cluster-info
```

### 2. Сборка образов Drifter и Drift-Checker

```bash
cd drifter

# Собираем образ Drifter
docker build -t nickosipov/drifter:latest .
docker push nickosipov/drifter:latest

cd ../drift-checker

# Собираем образ Drift-Checker
docker build -t nickosipov/drift-checker:latest .
docker push nickosipov/drift-checker:latest
```

### 3. Создание namespace

```bash
kubectl apply -f k8s/namespace.yaml
```

### 4. Создание Secrets

```bash
kubectl apply -n drift-detection -f k8s/secrets.yaml
```

### 5. Развертывание сервисов

```bash
# Развертываем PostgreSQL
kubectl apply -n drift-detection -f k8s/airflow-postgres.yaml

# Развертываем MinIO
kubectl apply -n drift-detection -f k8s/minio.yaml

# Инициализируем MinIO
kubectl apply -n drift-detection -f k8s/minio-init-job.yaml

# Развертываем MLflow
kubectl apply -n drift-detection -f k8s/mlflow.yaml

# Развертываем Drifter
kubectl apply -n drift-detection -f k8s/drifter.yaml

# Применяем Airflow RBAC
kubectl apply -n drift-detection -f k8s/airflow-rbac.yaml

# Развертываем Airflow
kubectl apply -n drift-detection -f k8s/airflow.yaml
```

### 6. Инициализация MinIO

```bash
# Запускаем Job для инициализации MinIO
# Job автоматически скачает референсные данные из GitHub и загрузит в MinIO
kubectl apply -n drift-detection -f k8s/minio-init-job.yaml

# Ждем завершения Job
kubectl wait --for=condition=complete --timeout=300s job/minio-init -n drift-detection

# Проверяем логи
kubectl logs -n drift-detection job/minio-init
```

### 7. Копирование DAG

```bash
# Копируем DAG в Airflow
./copy-dag.sh
```

### 8. Проверка статуса

```bash
# Проверяем состояние подов
kubectl get pods -n drift-detection

# Ждем, пока все поды будут в статусе Running
kubectl wait --for=condition=ready pod --all -n drift-detection --timeout=300s
```

### 9. Доступ к UI

**Port-forward (рекомендуется)**
```bash
# Пробрасываем порты (в отдельных терминалах)
kubectl port-forward -n drift-detection svc/airflow 8080:8080
kubectl port-forward -n drift-detection svc/mlflow 5000:5000
kubectl port-forward -n drift-detection svc/minio 9001:9001
```

Откройте в браузере:
- Airflow UI: http://localhost:8080 (admin/admin)
- MLflow UI: http://localhost:5000
- MinIO Console: http://localhost:9001 (minio/minio123)

## Проверка работы

### 1. Проверка Drifter

```bash
# Проверяем, что drifter отдает данные
kubectl run -it --rm curl --image=curlimages/curl --restart=Never -n drift-detection -- \
  curl http://drifter.drift-detection.svc.cluster.local/api/v1/data
```

### 2. Проверка Airflow

1. Откройте Airflow UI: http://localhost:8080
2. Войдите (admin/admin)
3. Найдите DAG `drift_detection`
4. Включите DAG (toggle справа)
5. Запустите вручную или дождитесь автоматического запуска

### 3. Проверка MLflow

1. Откройте MLflow UI: http://localhost:5000
2. Проверьте эксперименты и метрики дрифта
3. Посмотрите артефакты (datasets и HTML отчеты)

## Настройка

### Изменение вероятности дрифта

Отредактируйте `k8s/drifter.yaml`:

```yaml
env:
- name: DRIFT_PROB
  value: "0.8"  # Увеличить вероятность дрифта
```

Примените изменения:

```bash
kubectl apply -f k8s/drifter.yaml
kubectl rollout restart deployment/drifter -n drift-detection
```

### Изменение расписания проверок

Отредактируйте `k8s/configmaps.yaml`, измените параметр `schedule`:

```python
schedule="*/10 * * * *",  # Каждые 10 минут вместо 5
```

Примените изменения:

```bash
kubectl apply -f k8s/configmaps.yaml
kubectl rollout restart deployment/airflow -n drift-detection
```

## Логи и отладка

```bash
# Логи Airflow
kubectl logs -n drift-detection deployment/airflow -f

# Логи MLflow
kubectl logs -n drift-detection deployment/mlflow -f

# Логи Drifter
kubectl logs -n drift-detection deployment/drifter -f

# Логи PostgreSQL
kubectl logs -n drift-detection deployment/postgres -f

# Описание пода (для диагностики проблем)
kubectl describe pod -n drift-detection <pod-name>

# Подключение к PostgreSQL для отладки
kubectl exec -it -n drift-detection deployment/postgres -- psql -U airflow -d airflow
```

## Очистка

```bash
# Удаление всех ресурсов
kubectl delete namespace drift-detection

# Остановка и удаление Minikube кластера
minikube stop
minikube delete
```

## Структура проекта

```

├── drifter/                    # FastAPI приложение
│   ├── Dockerfile
│   ├── main.py
│   ├── settings.py
│   └── requirements.txt
├── dags/                       # Airflow DAGs
│   └── drift_detection.py
├── data/                       # Референсные данные
│   └── reference.csv
├── k8s/                        # Kubernetes манифесты
│   ├── namespace.yaml
│   ├── secrets.yaml
│   ├── postgres.yaml
│   ├── minio.yaml
│   ├── minio-init-job.yaml
│   ├── drifter.yaml
│   ├── airflow.yaml
│   └── mlflow.yaml
├── copy-dag.sh                # Копирование DAG
├── deploy.sh                  # Автоматическое развертывание
├── cleanup.sh                 # Удаление
└── README.md
```

## Дальнейшее развитие

Для production-окружения рекомендуется:

1. Использовать PostgreSQL для MLflow backend (сейчас SQLite)
2. Использовать CeleryExecutor/KubernetesExecutor для Airflow с несколькими workers
3. initContainers для инициализации MinIO
4. Настроить Ingress для доступа к сервисам
5. Использовать GitSync для DAGs вместо ручного копирования
6. Настроить PostgreSQL с репликацией и резервным копированием
7. Настроить мониторинг (Prometheus, Grafana)
8. Логирование и алерты при дрифте