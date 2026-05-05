# example_usage.py
import json
import time
import random
from kafka import KafkaProducer
import os
import logging
import threading
import subprocess

# --- Configuration ---
KAFKA_BROKER = 'localhost:9092'
RAW_IOT_TOPIC = 'raw_iot_data'
INITIAL_MODEL_PATH = 'anomaly_model.joblib' # Matches main.py

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def start_kafka_docker():
    """Starts Kafka and Zookeeper using docker-compose."""
    logging.info("Attempting to start Kafka and Zookeeper via Docker Compose...")
    try:
        # Check if docker-compose.yml exists, if not, create a minimal one
        if not os.path.exists("docker-compose.yml"):
            logging.info("docker-compose.yml not found, creating a default one.")
            with open("docker-compose.yml", "w") as f:
                f.write("""
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
"""
)
        
        # Bring up services
        subprocess.run(["docker-compose", "up", "-d"], check=True)
        logging.info("Kafka and Zookeeper started successfully.")
        time.sleep(10) # Give Kafka some time to initialize
    except subprocess.CalledProcessError as e:
        logging.error(f"Error starting Kafka via Docker Compose: {e}")
        logging.info("Assuming Kafka is already running or attempting to continue without Docker.")
    except FileNotFoundError:
        logging.error("docker-compose command not found. Please install Docker Compose or ensure Kafka is running manually.")
        logging.info("Attempting to continue assuming Kafka is running.")


def stop_kafka_docker():
    """Stops Kafka and Zookeeper using docker-compose."""
    logging.info("Stopping Kafka and Zookeeper via Docker Compose...")
    try:
        subprocess.run(["docker-compose", "down"], check=True)
        logging.info("Kafka and Zookeeper stopped.")
    except subprocess.CalledProcessError as e:
        logging.error(f"Error stopping Kafka via Docker Compose: {e}")
    except FileNotFoundError:
        logging.warning("docker-compose command not found. Please stop Kafka manually if it was started.")


class IoTSensorProducer:
    """
    Simulates an IoT sensor sending data to Kafka.
    Introduces anomalies and slow drift over time.
    """
    def __init__(self, broker, topic):
        self.producer = KafkaProducer(
            bootstrap_servers=[broker],
            value_serializer=lambda x: json.dumps(x).encode('utf-8')
        )
        self.topic = topic
        self.base_temp = 25.0
        self.base_pressure = 100.0
        self.base_vibration = 0.5
        self.drift_factor = 0.001
        self.message_count = 0

    def generate_data(self, introduce_anomaly=False, introduce_drift=False):
        if introduce_drift:
            self.base_temp += random.uniform(-0.1, 0.2) # Slowly change base temp
            self.base_pressure += random.uniform(-0.05, 0.1)
            self.base_vibration += random.uniform(-0.001, 0.005)
            logging.info(f"Introducing drift: new base temp={self.base_temp:.2f}")

        temperature = self.base_temp + random.uniform(-1.0, 1.0)
        pressure = self.base_pressure + random.uniform(-0.5, 0.5)
        vibration = self.base_vibration + random.uniform(-0.1, 0.1)

        if introduce_anomaly:
            # Create a clear anomaly
            temperature += random.uniform(5.0, 15.0) # Spike in temperature
            pressure += random.uniform(2.0, 5.0)     # Spike in pressure
            vibration += random.uniform(0.5, 1.5)    # Spike in vibration
            logging.warning("--- INTRODUCING ANOMALY ---")

        data = {
            'timestamp': time.time(),
            'temperature': temperature,
            'pressure': pressure,
            'vibration': vibration
        }
        return data

    def run(self):
        try:
            while True:
                self.message_count += 1
                introduce_anomaly = (self.message_count % 200 == 0) # Every 200 messages
                introduce_drift = (self.message_count % 1000 == 0) # Every 1000 messages
                
                data = self.generate_data(introduce_anomaly, introduce_drift)
                self.producer.send(self.topic, data)
                if self.message_count % 50 == 0:
                    logging.info(f"Sent {self.message_count} messages. Latest: {data['temperature']:.2f}°C, {data['pressure']:.2f}bar, {data['vibration']:.2f}G")
                time.sleep(0.1) # Send a message every 100ms
        except KeyboardInterrupt:
            logging.info("Producer stopped.")
        finally:
            self.producer.close()

def run_consumer_pipeline():
    """Runs the main anomaly detection pipeline."""
    logging.info("Starting Anomaly Detection Pipeline (main.py)...")
    try:
        # Use subprocess.Popen to run main.py in a separate process
        # This assumes main.py is in the current directory
        process = subprocess.Popen(['python', 'main.py'])
        process.wait() # Wait for the process to complete or be interrupted
    except KeyboardInterrupt:
        logging.info("Consumer pipeline process interrupted.")
    except Exception as e:
        logging.error(f"Error running consumer pipeline: {e}")
    finally:
        if 'process' in locals() and process.poll() is None:
            process.terminate()
            process.wait()


if __name__ == "__main__":
    # Ensure any old model file is removed for a clean start
    if os.path.exists(INITIAL_MODEL_PATH):
        os.remove(INITIAL_MODEL_PATH)
        logging.info(f"Removed old model file: {INITIAL_MODEL_PATH}")

    # 1. Start Kafka Docker containers
    start_kafka_docker()

    # 2. Run the consumer pipeline in a separate thread
    consumer_thread = threading.Thread(target=run_consumer_pipeline)
    consumer_thread.start()
    time.sleep(5) # Give consumer a moment to connect to Kafka

    # 3. Run the producer in the main thread
    producer = IoTSensorProducer(KAFKA_BROKER, RAW_IOT_TOPIC)
    logging.info("Starting IoT Sensor Data Producer...")
    producer.run()

    # 4. Wait for the consumer thread to finish (e.g., if interrupted)
    consumer_thread.join()

    # 5. Stop Kafka Docker containers
    stop_kafka_docker()
    logging.info("Demo finished.")
