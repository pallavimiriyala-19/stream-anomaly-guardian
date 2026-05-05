# Functionality: Stream Anomaly Guardian

This document details the core functionality, architecture, and design decisions behind the Stream Anomaly Guardian project.

## 1. Core Objective

The primary goal of Stream Anomaly Guardian is to provide a robust, real-time, and adaptive machine learning pipeline for detecting anomalies in streaming data, particularly focusing on industrial IoT sensor data. It addresses the challenges of concept drift by automatically retraining its models, ensuring continuous high performance in dynamic environments.

## 2. Architecture and Data Flow

The system is designed with a clear separation of concerns, utilizing Apache Kafka as the central nervous system for data ingestion and message passing.

### High-Level Data Flow:

1.  **Data Generation (Producer)**: Simulated IoT sensors (e.g., `producer.py` in `example_usage`) generate raw sensor readings (e.g., temperature, pressure, vibration) and push them as JSON messages to the `raw_iot_data` Kafka topic.
2.  **Data Ingestion & Processing (Consumer)**: The `AnomalyDetectionPipeline` in `main.py` acts as a Kafka consumer. It subscribes to the `raw_iot_data` topic, ingesting messages in real-time.
3.  **Real-time Feature Engineering**: For each incoming raw data point, the `FeatureTransformer` component within the pipeline maintains a sliding window of recent observations. It calculates statistical features (mean, standard deviation, min, max) over this window for each sensor reading, transforming raw data into a structured feature vector suitable for machine learning models.
4.  **Anomaly Inference**: The engineered feature vector is then fed into the current active anomaly detection model (e.g., Isolation Forest), managed by the `ModelManager`. The model predicts whether the current data point represents an anomaly or normal behavior.
5.  **Concept Drift Detection**: Concurrently with anomaly inference, a `ConceptDriftDetector` (using `river.drift.ADWIN`) continuously monitors a derived stream (e.g., the model's anomaly scores or key features). It tracks statistical changes in this stream, identifying when the underlying data distribution has shifted significantly.
6.  **Self-Healing Retraining Trigger**: If the `ConceptDriftDetector` signals a drift, the pipeline initiates a model retraining process.
7.  **Model Retraining**: The retraining mechanism uses a `retrain_buffer` that stores recent "normal" feature vectors. A new anomaly detection model is trained on this fresh, representative data.
8.  **Model Update**: Upon successful retraining, the `ModelManager` updates the active model, replacing the old, less relevant model with the newly trained one. The `ConceptDriftDetector` is also reset to learn from the new data distribution.
9.  **Anomaly Output/Alerting**: If an anomaly is detected, its details (timestamp, score, features, raw data) are published to a separate Kafka topic (`iot_anomalies`) for downstream alerting, logging, or further analysis.

```mermaid
graph TD
    subgraph Data Flow
        A[IoT Data Producer] -->|JSON messages| B(Kafka Topic: raw_iot_data)
        B --> C{AnomalyDetectionPipeline Consumer}
        C --> D[FeatureTransformer (Sliding Window)]
        D --> E[ModelManager (Current Model)]
        E --> F[Anomaly Detector (IsolationForest)]
        F --> G[Anomaly / Normal Output]
        F --> H{ConceptDriftDetector (ADWIN)}
        G --> J(Kafka Topic: iot_anomalies)
    end

    subgraph Retraining Flow
        H -- Drift Detected --> K[Retraining Trigger]
        K --> L[Retrain Buffer (Recent Normal Data)]
        L --> M[Model Retrainer (Trains New Model)]
        M -->|New Model| E
    end
```

## 3. Key Components and Design Decisions

*   **Kafka (`kafka-python`)**:
    *   **Choice**: Selected for its high-throughput, fault-tolerance, and distributed nature, making it ideal for real-time streaming data pipelines. It decouples the data producers from consumers, allowing for independent scaling and resilience.
    *   **Functionality**: Used for ingesting raw sensor data (`raw_iot_data`) and publishing detected anomalies (`iot_anomalies`).

*   **Feature Engineering (`FeatureTransformer`)**:
    *   **Choice**: A custom class implemented to handle sliding window aggregations. This is crucial for transforming discrete raw sensor readings into meaningful contextual features (e.g., trends, variability) over time.
    *   **Functionality**: Maintains a `deque` buffer for each sensor feature. When enough data accumulates, it computes statistical metrics (mean, std dev, min, max) over the window, providing a richer input for the anomaly model.

*   **Anomaly Detection Model (`scikit-learn.ensemble.IsolationForest`)**:
    *   **Choice**: Isolation Forest is well-suited for anomaly detection in high-dimensional datasets and is computationally efficient. It performs well in unsupervised settings where labeled anomaly data is scarce.
    *   **Functionality**: Trained on "normal" data to learn typical patterns. It assigns an anomaly score, where lower scores indicate a higher likelihood of being an outlier.

*   **Concept Drift Detection (`river.drift.ADWIN`)**:
    *   **Choice**: `river` (formerly `creme`) provides state-of-the-art online learning algorithms, including robust concept drift detectors. ADWIN (ADaptive WINdowing) is an excellent choice as it automatically adapts its window size based on changes in data distribution, making it sensitive to both gradual and abrupt drifts.
    *   **Functionality**: Continuously updates based on the stream of anomaly scores (or other relevant metrics). When a statistically significant change is detected in the stream's properties, it signals a drift.

*   **Model Management (`ModelManager`)**:
    *   **Choice**: A simple local file-based manager using `joblib` for serialization. For production, this would typically integrate with a dedicated MLOps platform (e.g., MLflow, Sagemaker Model Registry).
    *   **Functionality**: Handles saving the trained model to disk and loading the latest version, ensuring that the pipeline always uses the most up-to-date model.

*   **Self-Healing Retraining**:
    *   **Mechanism**: This is the "self-healing" aspect. When ADWIN detects drift, the pipeline automatically triggers a `_retrain_model` function. This function uses the `retrain_buffer` (which stores recent feature vectors, assumed to represent the new "normal" operating conditions post-drift) to train a fresh instance of the Isolation Forest model.
    *   **Benefits**: Ensures that the anomaly detection system remains accurate and relevant even as the underlying operational conditions or sensor characteristics evolve over time, reducing false positives and negatives.

*   **Retrain Buffer (`deque`)**:
    *   **Choice**: A `deque` (double-ended queue) with a fixed maximum length is used to efficiently store the most recent feature vectors. This prevents memory issues and ensures that retraining always uses the most current data.
    *   **Functionality**: Provides a rolling window of data points for retraining, capturing the post-drift "normal" behavior.

## 4. Scalability Considerations

*   **Kafka**: Inherently scalable for high-throughput data ingestion. Multiple consumer instances can be run in a consumer group to distribute the processing load.
*   **Modular Design**: The `AnomalyDetectionPipeline` is self-contained. In a production environment, the feature engineering, anomaly detection, and drift detection components could be further separated into distinct microservices or FaaS (Function-as-a-Service) components.
*   **Model Retraining**: The current implementation triggers retraining directly within the consumer. For very large datasets or complex models, retraining could be offloaded to a separate, asynchronous job queue (e.g., using Celery, Kubernetes Jobs) to avoid blocking the real-time inference stream.

## 5. Future Enhancements

*   **More Sophisticated Feature Engineering**: Incorporate time-series specific features (e.g., Fourier transforms, autocorrelation, lag features).
*   **Ensemble Models**: Use an ensemble of different anomaly detection algorithms or dynamically select the best model based on recent performance.
*   **External Model Registry**: Integrate with MLOps tools like MLflow or Kubeflow for robust model versioning and deployment.
*   **Alerting Integration**: Connect the `iot_anomalies` topic to external alerting systems (e.g., Slack, PagerDuty).
*   **Distributed Retraining**: Implement retraining using Spark or Dask for larger datasets.
*   **Explainable AI (XAI)**: Add methods to explain *why* a specific data point was flagged as an anomaly, providing more actionable insights.
