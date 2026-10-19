CREATE DATABASE IF NOT EXISTS olist_oltp
  CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
USE olist_oltp;

SET FOREIGN_KEY_CHECKS = 0;
DROP TABLE IF EXISTS order_reviews;
DROP TABLE IF EXISTS order_payments;
DROP TABLE IF EXISTS order_items;
DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS products;
DROP TABLE IF EXISTS sellers;
DROP TABLE IF EXISTS customers;
DROP TABLE IF EXISTS geolocation;
DROP TABLE IF EXISTS category_translation;
SET FOREIGN_KEY_CHECKS = 1;

CREATE TABLE customers (
  customer_id CHAR(32) PRIMARY KEY,
  customer_unique_id CHAR(32) NOT NULL,
  customer_zip_code_prefix CHAR(5),
  customer_city VARCHAR(255),
  customer_state CHAR(2),
  source_file VARCHAR(255) NOT NULL,
  source_ingested_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  source_updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  source_row_hash CHAR(64),
  INDEX idx_customers_unique (customer_unique_id),
  INDEX idx_customers_updated (source_updated_at)
) ENGINE=InnoDB;

CREATE TABLE sellers (
  seller_id CHAR(32) PRIMARY KEY,
  seller_zip_code_prefix CHAR(5),
  seller_city VARCHAR(255),
  seller_state CHAR(2),
  source_file VARCHAR(255) NOT NULL,
  source_ingested_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  source_updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  source_row_hash CHAR(64),
  INDEX idx_sellers_updated (source_updated_at)
) ENGINE=InnoDB;

CREATE TABLE category_translation (
  product_category_name VARCHAR(255) PRIMARY KEY,
  product_category_name_english VARCHAR(255),
  source_file VARCHAR(255) NOT NULL,
  source_ingested_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  source_updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  source_row_hash CHAR(64),
  INDEX idx_category_updated (source_updated_at)
) ENGINE=InnoDB;

CREATE TABLE products (
  product_id CHAR(32) PRIMARY KEY,
  product_category_name VARCHAR(255),
  product_name_lenght INT,
  product_description_lenght INT,
  product_photos_qty INT,
  product_weight_g DECIMAL(12,3),
  product_length_cm DECIMAL(12,3),
  product_height_cm DECIMAL(12,3),
  product_width_cm DECIMAL(12,3),
  source_file VARCHAR(255) NOT NULL,
  source_ingested_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  source_updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  source_row_hash CHAR(64),
  INDEX idx_products_category (product_category_name),
  INDEX idx_products_updated (source_updated_at)
) ENGINE=InnoDB;

CREATE TABLE orders (
  order_id CHAR(32) PRIMARY KEY,
  customer_id CHAR(32) NOT NULL,
  order_status VARCHAR(32) NOT NULL,
  order_purchase_timestamp DATETIME,
  order_approved_at DATETIME,
  order_delivered_carrier_date DATETIME,
  order_delivered_customer_date DATETIME,
  order_estimated_delivery_date DATETIME,
  source_file VARCHAR(255) NOT NULL,
  source_ingested_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  source_updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  source_row_hash CHAR(64),
  CONSTRAINT fk_oltp_order_customer FOREIGN KEY (customer_id) REFERENCES customers(customer_id),
  INDEX idx_orders_purchase (order_purchase_timestamp),
  INDEX idx_orders_updated (source_updated_at)
) ENGINE=InnoDB;

CREATE TABLE order_items (
  order_id CHAR(32) NOT NULL,
  order_item_id INT NOT NULL,
  product_id CHAR(32) NOT NULL,
  seller_id CHAR(32) NOT NULL,
  shipping_limit_date DATETIME,
  price DECIMAL(14,2),
  freight_value DECIMAL(14,2),
  source_file VARCHAR(255) NOT NULL,
  source_ingested_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  source_updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  source_row_hash CHAR(64),
  PRIMARY KEY (order_id, order_item_id),
  CONSTRAINT fk_oltp_item_order FOREIGN KEY (order_id) REFERENCES orders(order_id),
  CONSTRAINT fk_oltp_item_product FOREIGN KEY (product_id) REFERENCES products(product_id),
  CONSTRAINT fk_oltp_item_seller FOREIGN KEY (seller_id) REFERENCES sellers(seller_id),
  INDEX idx_items_updated (source_updated_at)
) ENGINE=InnoDB;

CREATE TABLE order_payments (
  order_id CHAR(32) NOT NULL,
  payment_sequential INT NOT NULL,
  payment_type VARCHAR(32),
  payment_installments INT,
  payment_value DECIMAL(14,2),
  source_file VARCHAR(255) NOT NULL,
  source_ingested_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  source_updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  source_row_hash CHAR(64),
  PRIMARY KEY (order_id, payment_sequential),
  CONSTRAINT fk_oltp_payment_order FOREIGN KEY (order_id) REFERENCES orders(order_id),
  INDEX idx_payments_updated (source_updated_at)
) ENGINE=InnoDB;

CREATE TABLE order_reviews (
  source_row_id BIGINT AUTO_INCREMENT PRIMARY KEY,
  review_id CHAR(32) NOT NULL,
  order_id CHAR(32) NOT NULL,
  review_score TINYINT,
  review_comment_title TEXT,
  review_comment_message LONGTEXT,
  review_creation_date DATETIME,
  review_answer_timestamp DATETIME,
  source_file VARCHAR(255) NOT NULL,
  source_ingested_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  source_updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  source_row_hash CHAR(64),
  CONSTRAINT fk_oltp_review_order FOREIGN KEY (order_id) REFERENCES orders(order_id),
  INDEX idx_reviews_id (review_id),
  INDEX idx_reviews_updated (source_updated_at)
) ENGINE=InnoDB;

CREATE TABLE geolocation (
  source_row_id BIGINT AUTO_INCREMENT PRIMARY KEY,
  geolocation_zip_code_prefix CHAR(5),
  geolocation_lat DOUBLE,
  geolocation_lng DOUBLE,
  geolocation_city VARCHAR(255),
  geolocation_state CHAR(2),
  source_file VARCHAR(255) NOT NULL,
  source_ingested_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  source_updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  source_row_hash CHAR(64),
  INDEX idx_geo_zip (geolocation_zip_code_prefix),
  INDEX idx_geo_updated (source_updated_at)
) ENGINE=InnoDB;
