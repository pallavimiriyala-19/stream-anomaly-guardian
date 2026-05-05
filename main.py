# main.py
import json
import time
import numpy as np
import pandas as pd
from kafka import KafkaConsumer, KafkaProducer
from sklearn.ensemble import IsolationForest
from river import drift
import joblib
import os
import logging
from collections import deque

# --- Configuration ---
KAFKA_BROKER = 'localhost:9092'
RAW_IOT_TOPIC = 'raw_iot_data'
ANOMALY_TOPIC = 'iot_anomalies'
MODEL_PATH = 'anomaly_model.joblib'
WINDOW_SIZE = 100 # Number of data points for feature engineering window
RETRAIN_THRESHOLD = 0.05 # ADWIN drift detection threshold
RETRAIN_DATA_BUFFER_SIZE = 5000 # Number of samples to keep for retraining
INITIAL_MODEL_TRAINING_SIZE = 500 # Initial samples to train model

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Helper Functions and Classes ---

class FeatureTransformer:
    """
    Transforms raw sensor data into features suitable for anomaly detection.
    Uses a sliding window approach.
    """
    def __init__(self, window_size: int, feature_names: list):
        self.window_size = window_size
        self.feature_names = feature_names
        self.data_buffer = {name: deque(maxlen=window_size) for name in feature_names}

    def add_sample(self, data_point: dict):
        for name in self.feature_names:
            if name in data_point:
                self.data_buffer[name].append(data_point[name])

    def get_features(self) -> pd.DataFrame | None:
        if any(len(dq) < self.window_size for dq in self.data_buffer.values()):
            return None # Not enough data for a full window

        features = {}
        for name in self.feature_names:
            window_data = np.array(self.data_buffer[name])
            features[f'{name}_mean'] = np.mean(window_data)
            features[f'{name}_std'] = np.std(window_data)
            features[f'{name}_min'] = np.min(window_data)
            features[f'{name}_max'] = np.max(window_data)
            # Add more complex features as needed, e.g., FFT, rate of change
        
        return pd.DataFrame([features])

class ModelManager:
    """
    Manages the lifecycle of the anomaly detection model.
    Handles loading, saving, and providing the active model.
    """
    def __init__(self, model_path: str):
        self.model_path = model_path
        self._model = None
        self._load_model()

    def _load_model(self):
        if os.path.exists(self.model_path):
            self._model = joblib.load(self.model_path)
            logging.info(f"Model loaded from {self.model_path}")
        else:
            logging.warning(f"No model found at {self.model_path}. A new model will be trained.")
            self._model = None # Will be initialized by initial training

    def save_model(self, model):
        joblib.dump(model, self.model_path)
        self._model = model
        logging.info(f"Model saved to {self.model_path}")

    def get_model(self):
        return self._model

    def set_model(self, model):
        self._model = model

class AnomalyDetectionPipeline:
    """
    Main pipeline for real-time anomaly detection, concept drift, and self-healing.
    """
    def __init__(self,
                 kafka_broker: str,
                 raw_topic: str,
                 anomaly_topic: str,
                 model_path: str,
                 window_size: int,
                 feature_names: list):

        self.consumer = KafkaConsumer(
            raw_topic,
            bootstrap_servers=[kafka_broker],
            auto_offset_reset='latest',
            enable_auto_commit=True,
            value_deserializer=lambda x: json.loads(x.decode('utf-8'))
        )
        self.producer = KafkaProducer(
            bootstrap_servers=[kafka_broker],
            value_serializer=lambda x: json.dumps(x).encode('utf-8')
        )
        self.model_manager = ModelManager(model_path)
        self.feature_transformer = FeatureTransformer(window_size, feature_names)
        self.drift_detector = drift.ADWIN(delta=RETRAIN_THRESHOLD)
        self.retrain_buffer = deque(maxlen=RETRAIN_DATA_BUFFER_SIZE)
        self.anomaly_topic = anomaly_topic
        self.feature_names = feature_names
        self.initial_training_data = [] # Buffer for initial model training
        self.is_initial_training_done = False

        logging.info(f"Pipeline initialized. Consuming from {raw_topic}, producing to {anomaly_topic}")

    def _train_initial_model(self):
        logging.info("Gathering data for initial model training...")
        # For initial training, we might consume some messages in blocking mode
        # or assume some historical data is available.
        # For this demo, we'll just wait for enough messages from the stream.
        while len(self.initial_training_data) < INITIAL_MODEL_TRAINING_SIZE:
            msg = next(self.consumer) # Block until a message is received
            data_point = msg.value
            self.feature_transformer.add_sample(data_point)
            features_df = self.feature_transformer.get_features()
            if features_df is not None:
                self.initial_training_data.append(features_df.iloc[0])
            logging.info(f"Collected {len(self.initial_training_data)}/{INITIAL_MODEL_TRAINING_SIZE} for initial training.")
        
        X_train = pd.DataFrame(self.initial_training_data)
        logging.info(f"Training initial Isolation Forest model with {len(X_train)} samples...")
        model = IsolationForest(contamination='auto', random_state=42)
        model.fit(X_train)
        self.model_manager.save_model(model)
        self.is_initial_training_done = True
        logging.info("Initial model training complete.")

    def _retrain_model(self):
        logging.info("Concept drift detected! Triggering model retraining...")
        if not self.retrain_buffer:
            logging.warning("Retrain buffer is empty. Cannot retrain model.")
            return

        # Use data from the retrain buffer (assumed to be recent 'normal' data)
        retrain_data = pd.DataFrame(list(self.retrain_buffer))
        
        logging.info(f"Retraining Isolation Forest model with {len(retrain_data)} samples from buffer.")
        # Re-initialize ADWIN
        self.drift_detector = drift.ADWIN(delta=RETRAIN_THRESHOLD)
        
        new_model = IsolationForest(contamination='auto', random_state=42)
        new_model.fit(retrain_data)
        self.model_manager.save_model(new_model)
        logging.info("Model retraining complete. New model is active.")
        # Clear the buffer after retraining if desired, or let it manage its maxlen

    def run(self):
        if not self.model_manager.get_model():
            self._train_initial_model()

        logging.info("Starting anomaly detection stream processing...")
        for message in self.consumer:
            data_point = message.value
            timestamp = data_point.get('timestamp', time.time())
            
            self.feature_transformer.add_sample(data_point)
            features_df = self.feature_transformer.get_features()

            if features_df is None:
                continue # Not enough data in window yet

            # Add features to retraining buffer
            self.retrain_buffer.append(features_df.iloc[0])

            model = self.model_manager.get_model()
            if model is None:
                logging.warning("Model not available, skipping anomaly detection.")
                continue

            # Anomaly Detection
            try:
                # Isolation Forest returns -1 for anomalies, 1 for normal
                anomaly_score = model.decision_function(features_df)[0]
                is_anomaly = model.predict(features_df)[0] == -1
            except Exception as e:
                logging.error(f"Error during anomaly detection: {e}")
                continue

            # Concept Drift Detection (on anomaly score or feature values)
            # For simplicity, we use the anomaly score itself as the input for ADWIN.
            # In a real scenario, you might monitor specific features or model residuals.
            self.drift_detector.update(anomaly_score)
            if self.drift_detector.drift_detected_:
                logging.info(f"ADWIN detected concept drift at index {self.drift_detector.n_updates}")
                self._retrain_model()
                # Reset drift detector after retraining
                self.drift_detector = drift.ADWIN(delta=RETRAIN_THRESHOLD)

            if is_anomaly:
                anomaly_details = {
                    'timestamp': timestamp,
                    'is_anomaly': True,
                    'anomaly_score': float(anomaly_score),
                    'features': features_df.iloc[0].to_dict(),
                    'raw_data': data_point
                }
                self.producer.send(self.anomaly_topic, anomaly_details)
                logging.warning(f"ANOMALY DETECTED: {anomaly_details['anomaly_score']:.2f} at {timestamp}")
            else:
                # Log normal operations, perhaps less frequently
                # logging.info(f"Normal operation (Score: {anomaly_score:.2f})")
                pass

if __name__ == "__main__":
    # Define the sensor features we expect to receive and use for training
    # For a real IoT scenario, these would be specific sensor readings
    sensor_features = ['temperature', 'pressure', 'vibration'] 

    # Clean up previous model if exists
    if os.path.exists(MODEL_PATH):
        os.remove(MODEL_PATH)

    pipeline = AnomalyDetectionPipeline(
        kafka_broker=KAFKA_BROKER,
        raw_topic=RAW_IOT_TOPIC,
        anomaly_topic=ANOMALY_TOPIC,
        model_path=MODEL_PATH,
        window_size=WINDOW_SIZE,
        feature_names=sensor_features
    )
    
    try:
        pipeline.run()
    except KeyboardInterrupt:
        logging.info("Pipeline stopped by user.")
    finally:
        pipeline.consumer.close()
        pipeline.producer.close()
        logging.info("Kafka resources closed.")
