from airflow import DAG
from airflow.providers.cncf.kubernetes.operators.pod import KubernetesPodOperator
from airflow.providers.cncf.kubernetes.secret import Secret
from airflow.utils.dates import days_ago


with DAG(
    dag_id="drift_detection",
    description="Проверка дрифта данных с использованием Evidently",
    start_date=days_ago(1),
    schedule="0 * * * *",  # Каждый час
    catchup=False,
    tags=["drift", "monitoring"],
) as dag:
    
    # Секреты для MinIO
    aws_access_key = Secret(
        deploy_type="env",
        deploy_target="AWS_ACCESS_KEY_ID",
        secret="minio-credentials",
        key="AWS_ACCESS_KEY_ID",
    )
    
    aws_secret_key = Secret(
        deploy_type="env",
        deploy_target="AWS_SECRET_ACCESS_KEY",
        secret="minio-credentials",
        key="AWS_SECRET_ACCESS_KEY",
    )
    
    check_drift_task = KubernetesPodOperator(
        task_id="drift-checker",
        name="drift-checker",
        image="drift-checker:latest",
        image_pull_policy="IfNotPresent",
        service_account_name="airflow",
        env_vars={
            "DRIFTER_URL": "http://drifter.drift-detection.svc.cluster.local/api/v1/data",
            "MLFLOW_TRACKING_URI": "http://mlflow.drift-detection.svc.cluster.local:5000",
            "MLFLOW_S3_ENDPOINT_URL": "http://minio.drift-detection.svc.cluster.local:9000",
            "REFERENCE_DATA_S3_PATH": "s3://datasets/reference.csv",
        },
        secrets=[aws_access_key, aws_secret_key],
        get_logs=True,
        is_delete_operator_pod=True,
    )
