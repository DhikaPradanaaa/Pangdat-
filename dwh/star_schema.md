# Olist star schema

```mermaid
erDiagram
    DIM_DATE ||--o{ FACT_ORDER : purchase_date
    DIM_DATE ||--o{ FACT_SALES : purchase_date
    DIM_DATE ||--o{ FACT_PAYMENT : purchase_date
    DIM_DATE ||--o{ FACT_REVIEW : creation_date
    DIM_GEOLOCATION ||--o{ DIM_CUSTOMER : location
    DIM_GEOLOCATION ||--o{ DIM_SELLER : location
    DIM_CUSTOMER ||--o{ FACT_ORDER : places
    FACT_ORDER ||--o{ FACT_SALES : contains
    FACT_ORDER ||--o{ FACT_PAYMENT : paid_by
    FACT_ORDER ||--o{ FACT_REVIEW : reviewed_by
    DIM_PRODUCT ||--o{ FACT_SALES : product
    DIM_SELLER ||--o{ FACT_SALES : seller
```

## Grain

| Tabel | Grain |
|---|---|
| `dim_customer` | Satu `customer_id` |
| `dim_seller` | Satu `seller_id` |
| `dim_product` | Satu `product_id` |
| `dim_geolocation` | Satu prefix kode pos kanonis |
| `dim_date` | Satu tanggal kalender |
| `fact_order` | Satu `order_id` |
| `fact_sales` | Satu kombinasi `order_id` dan `order_item_id` |
| `fact_payment` | Satu kombinasi `order_id` dan `payment_sequential` |
| `fact_review` | Satu `review_key` komposit |

## Aturan penggunaan

`fact_sales`, `fact_payment`, dan `fact_review` memiliki grain berbeda. Untuk laporan yang membutuhkan ketiganya, agregasikan masing-masing fakta ke tingkat pesanan terlebih dahulu atau gunakan `vw_order_summary`. Penggabungan langsung ketiga tabel dapat menggandakan nilai pembayaran, penjualan, atau jumlah ulasan.

Surrogate key bernilai `0` adalah anggota `unknown`. Nilai ini digunakan jika referensi dimensi tidak tersedia, sehingga foreign key fakta tetap valid tanpa membuat nilai sumber palsu.
