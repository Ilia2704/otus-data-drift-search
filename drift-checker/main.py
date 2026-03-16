import json
import os
import tempfile
from pathlib import Path

import mlflow
import pandas as pd
import s3fs
from evidently import ColumnMapping
from evidently.metric_preset import DataDriftPreset
from evidently.report import Report


def extract_drift_result(report_dict: dict) -> dict:
    """
    Find the metric block that contains dataset drift summary
    and per-column drift information.
    """
    metrics = report_dict.get("metrics", [])

    for metric in metrics:
        result = metric.get("result", {})
        if (
            isinstance(result, dict)
            and "dataset_drift" in result
            and "number_of_drifted_columns" in result
            and "share_of_drifted_columns" in result
            and "drift_by_columns" in result
        ):
            return result

    raise ValueError(
        "Could not find drift result block in Evidently report output."
    )


def main():
    """Run data drift detection and log results to MLflow."""

    drifter_url = os.environ.get(
        "DRIFTER_URL",
        "http://drifter.drift-detection.svc.cluster.local/api/v1/data",
    )
    mlflow_uri = os.environ.get(
        "MLFLOW_TRACKING_URI",
        "http://mlflow.drift-detection.svc.cluster.local:5000",
    )
    reference_data_path = os.environ.get(
        "REFERENCE_DATA_S3_PATH",
        "s3://datasets/reference.csv",
    )

    aws_access_key_id = os.environ["AWS_ACCESS_KEY_ID"]
    aws_secret_access_key = os.environ["AWS_SECRET_ACCESS_KEY"]
    s3_endpoint_url = os.environ["MLFLOW_S3_ENDPOINT_URL"]

    print("Configuring MLflow...")
    mlflow.set_tracking_uri(mlflow_uri)

    print("Connecting to S3-compatible storage (MinIO)...")
    s3 = s3fs.S3FileSystem(
        key=aws_access_key_id,
        secret=aws_secret_access_key,
        use_ssl=False,
        client_kwargs={"endpoint_url": s3_endpoint_url},
    )

    print("Loading reference dataset from MinIO...")
    with s3.open(reference_data_path, "rb") as f:
        reference_df = pd.read_csv(f)

    print(f"Reference dataset loaded: shape={reference_df.shape}")
    print(reference_df.head())

    print("Loading current dataset from drifter service...")
    current_df = pd.read_csv(drifter_url)

    print(f"Current dataset loaded: shape={current_df.shape}")
    print(current_df.head())

    print("Preparing column mapping...")
    column_mapping = ColumnMapping()
    column_mapping.numerical_features = list(reference_df.columns)

    print("Generating Evidently drift report...")
    data_drift_report = Report(metrics=[DataDriftPreset()])
    data_drift_report.run(
        current_data=current_df,
        reference_data=reference_df,
        column_mapping=column_mapping,
    )

    report_dict = data_drift_report.as_dict()
    drift_result = extract_drift_result(report_dict)

    print("Logging results to MLflow...")

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_dir_path = Path(tmp_dir)

        # Save current dataset as artifact
        dataset_path = tmp_dir_path / "current-dataset.csv"
        current_df.to_csv(dataset_path, index=False)

        # Save Evidently HTML report as artifact
        html_path = tmp_dir_path / "evidently_report.html"
        data_drift_report.save_html(str(html_path))

        # Save raw report JSON as artifact for debugging
        json_path = tmp_dir_path / "evidently_report.json"
        json_path.write_text(
            json.dumps(report_dict, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        with mlflow.start_run() as run:
            # Log summary parameters and metrics
            mlflow.log_param("dataset_drift", drift_result["dataset_drift"])

            mlflow.log_metrics(
                {
                    "number_of_drifted_columns": drift_result["number_of_drifted_columns"],
                    "share_of_drifted_columns": drift_result["share_of_drifted_columns"],
                }
            )

            # Log per-feature drift score
            drift_by_columns = drift_result.get("drift_by_columns", {})
            for feature in column_mapping.numerical_features:
                feature_result = drift_by_columns.get(feature, {})
                drift_score = feature_result.get("drift_score")

                if drift_score is not None:
                    mlflow.log_metric(f"drift_score_{feature}", drift_score)

            # Log artifacts
            mlflow.log_artifact(str(dataset_path), artifact_path="datasets")
            mlflow.log_artifact(str(html_path), artifact_path="evidently")
            mlflow.log_artifact(str(json_path), artifact_path="evidently")

            print(f"MLflow Run ID: {run.info.run_id}")
            print(f"Detected dataset drift: {drift_result['dataset_drift']}")
            print(
                f"Number of drifted columns: {drift_result['number_of_drifted_columns']}"
            )
            print(
                f"Share of drifted columns: {drift_result['share_of_drifted_columns']:.2%}"
            )
            print(
                "Evidently HTML report saved as artifact: "
                "evidently/evidently_report.html"
            )


if __name__ == "__main__":
    main()