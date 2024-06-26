from airflow import DAG
from datetime import datetime, timedelta
from airflow.operators.dummy import DummyOperator
from airflow.operators.python_operator import PythonOperator
from airflow.providers.google.cloud.operators.dataproc import DataprocCreateClusterOperator
from airflow.providers.google.cloud.operators.dataproc import DataprocSubmitJobOperator
from airflow.providers.google.cloud.operators.dataproc import DataprocDeleteClusterOperator
from airflow.providers.google.cloud.transfers.gcs_to_bigquery import GCSToBigQueryOperator
from src.data_extraction.coin_api import CoinAPI
from src.data_processing.pyspark_processing import PysparkProcessor
from src.utils.gcs_handler import GCSHandler
from config.settings import *

default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'start_date': datetime(2024, 1, 19),
    'email': ['navalesnahuel@gmail.com'],
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

with DAG("CryptoAPI_dag",
         default_args=default_args,
         description='Dag for my Crypto Project',
         schedule_interval=timedelta(days=1),
         catchup=False) as dag:
    start = DummyOperator(task_id='start', dag=dag)

    get_data = PythonOperator(
        task_id='get_data_task',
        python_callable=CoinAPI(api_key).get_top_assets_data,
        op_args=[50],
        dag=dag
    )

    upload_to_gcs_task = PythonOperator(
        task_id='upload_to_gcs_task',
        python_callable=GCSHandler(bucket_name).upload_file,
        op_args=[local_file_path, remote_file_path],
        dag=dag,
    )

    create_cluster = DataprocCreateClusterOperator(
        task_id="create_cluster",
        project_id=PROJECT_ID,
        cluster_config=CLUSTER_CONFIG,
        region=REGION,
        cluster_name=CLUSTER_NAME,
    )

    pyspark_transform = DataprocSubmitJobOperator(
        task_id="pyspark_task",
        job=PYSPARK_JOB,
        region=REGION,
        project_id=PROJECT_ID
    )

    delete_cluster = DataprocDeleteClusterOperator(
        task_id="delete_cluster",
        project_id=PROJECT_ID,
        cluster_name=CLUSTER_NAME,
        region=REGION
    )

    gcs_to_gbq = GCSToBigQueryOperator(
        task_id="transfer_data_to_bigquery",
        bucket="data-bucket-crypto",
        source_objects=["transformed-data/part-*.snappy.parquet"],
        destination_project_dataset_table="crypto_dataset.crypto{}".format(datetime.now().strftime('%Y-%m-%d')),
        source_format="PARQUET",
        write_disposition="WRITE_TRUNCATE",
        create_disposition="CREATE_IF_NEEDED",
    )

    end = DummyOperator(task_id='end', dag=dag)

    start >> get_data >> upload_to_gcs_task >> create_cluster >> pyspark_transform >> delete_cluster >> gcs_to_gbq >> end
