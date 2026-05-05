# Stream Anomaly Guardian

[![License](https://img.shields.io/github/license/yourusername/stream-anomaly-guardian)](LICENSE)
[![Python Version](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![Build Status](https://github.com/yourusername/stream-anomaly-guardian/workflows/Python%20CI/badge.svg)](https://github.com/yourusername/stream-anomaly-guardian/actions)

## 🚀 Overview

**Stream Anomaly Guardian** is a cutting-edge open-source project designed to provide a robust, real-time, and adaptive machine learning pipeline for anomaly detection in streaming industrial IoT sensor data. Leveraging modern MLOps principles, this system automatically detects concept drift and triggers self-healing model retraining, ensuring peak performance and reliability in dynamic environments.

Imagine preventing equipment failure before it happens, optimizing operational efficiency, and reducing costly downtime. That's the power Stream Anomaly Guardian brings to your data streams.

## ✨ Features

*   **Real-time Processing**: Ingest and process high-velocity sensor data streams using Apache Kafka.
*   **Adaptive ML Models**: Utilizes `scikit-learn` models for anomaly detection, capable of adapting to changing data patterns.
*   **Concept Drift Detection**: Integrates `river`'s robust algorithms (e.g., ADWIN) to continuously monitor data distribution and model performance for drift.
*   **Self-Healing Retraining**: Automatically triggers model retraining when concept drift is detected, using recent, relevant data to maintain accuracy.
*   **Modular Architecture**: Designed for extensibility and easy integration into existing data ecosystems.
*   **Scalable**: Built on Kafka for high throughput and horizontal scalability.
*   **Explainable Anomalies**: Provides insights into *why* an anomaly was detected (e.g., specific feature values).

## 🛠️ Installation

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/yourusername/stream-anomaly-guardian.git
    cd stream-anomaly-guardian
    ```

2.  **Create a virtual environment (recommended):**
    ```bash
    python -m venv .venv
    source .venv/bin/activate # On Windows: .venv\Scripts\activate
    ```

3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Set up Apache Kafka:**
    You'll need a running Kafka instance. The easiest way for local development is via Docker Compose. If you don't have a `docker-compose.yml`, the `example_usage.py` script can generate a basic one for you.

    To manually set up Kafka with Docker Compose, create a `docker-compose.yml` file in your project root with the following content:

    ```yaml
    # docker-compose.yml
    version: '3'
    services:
      zookeeper:
        image: confluentinc/cp-zookeeper:latest
        environment:
          ZOOKEEPER_CLIENT_PORT: 2181
          ZOOKEEPER_TICK_TIME: 2000
        ports:
          - "2181:2181"

      kafka:
        image: confluentinc/cp-kafka:latest
        depends_on:
          - zookeeper
        ports:
          - "9092:9092"
        environment:
          KAFKA_BROKER_ID: 1
          KAFKA_ZOOKEEPER_CONNECT: zookeeper:2181
          KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://localhost:9092
          KAFKA_LISTENERS: PLAINTEXT://0.0.0.0:9092
          KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR: 1
          KAFKA_NUM_PARTITIONS: 1
    ```
    Then, from the directory containing `docker-compose.yml`, run:
    ```bash
    docker-compose up -d
    ```

## 🚀 Usage

The project includes an `example_usage.py` script that orchestrates the entire demo: it can start Kafka (if Docker Compose is configured), runs a simulated IoT data producer, and concurrently runs the anomaly detection pipeline consumer. This provides a full end-to-end demonstration.

To run the full demo:

```bash
python example_usage.py
```

Alternatively, you can run components separately:

1.  **Ensure Kafka is running** (see Installation Step 4).

2.  **Start the Anomaly Detection Consumer (in one terminal):**
    ```bash
    python main.py
    ```

3.  **Start the IoT Data Producer (in another terminal):**
    *(Note: The producer logic is embedded in `example_usage.py` for a full demo, but can be extracted or simplified for separate execution.)*

    ```bash
    python -c "from example_usage import IoTSensorProducer, KAFKA_BROKER, RAW_IOT_TOPIC; producer = IoTSensorProducer(KAFKA_BROKER, RAW_IOT_TOPIC); producer.run()"
    ```

The consumer will start processing messages from Kafka, performing anomaly detection. When concept drift is detected, it will automatically trigger a model retraining process, which will be logged to the console.

## 🏗️ Architecture

The system follows a microservices-inspired architecture, primarily built around Apache Kafka for messaging.

```mermaid
graph TD
    A[IoT Sensors (Simulated)] -->|Stream Data| B(Kafka Topic: raw_iot_data)
    B --> C{AnomalyDetectionPipeline Consumer}
    C --> D[Feature Engineering (Sliding Window)]
    D --> E[Adaptive Anomaly Detector]
    E --> F{Concept Drift Detector (ADWIN)}
    F --> G{Model Manager}
    G --> H[Anomaly Alerts / Outputs]
    F -- Drift Detected --> J[Model Retrainer]
    J --> K[Historical Data Store]
    K --> J
    J -->|New Model| G
```

*   **Data Producer**: Simulates IoT devices, pushing sensor readings to Kafka.
*   **Kafka**: Acts as the central nervous system, decoupling producers from consumers and providing high-throughput, fault-tolerant messaging.
*   **AnomalyDetectionPipeline Consumer**: The core application logic. It consumes raw data, performs real-time feature engineering (e.g., calculating statistical aggregates over sliding windows), and feeds these features into the anomaly detection model.
*   **Concept Drift Detector**: Continuously monitors the incoming data distribution and model performance. Upon detecting significant drift, it signals the need for retraining.
*   **Model Manager**: Handles loading, saving, and serving the current active anomaly detection model.
*   **Model Retrainer**: An asynchronous component (or a specific process triggered) that trains a new model on a fresh batch of historical (or recent "normal") data.
*   **Anomaly Alerts / Outputs**: Detected anomalies are logged, printed, or can be pushed to another Kafka topic for further alerting systems.

## 🤝 Contributing

We welcome contributions! Please see our `CONTRIBUTING.md` (future addition) for guidelines on how to submit pull requests, report bugs, and suggest features.

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
