# EXPLAIN ANALYZE de los índices de `ref`

Generado por `python -m data_pipeline.quality.explain_indexes`. PostgreSQL 17.9 (Debian 17.9-1.pgdg13+1), 4,425,008 transacciones. Cliente de prueba: el de más transacciones (150). Identificadores reemplazados por marcadores.

## `ix_transactions_customer_id_transaction_date`

Consulta: search_transactions: ventana de fechas del cliente, más recientes primero.

```sql
SELECT transaction_id, transaction_date, amount, currency, merchant_name, channel, transaction_type, transaction_status, product_id FROM ref.transactions WHERE customer_id = %(cid)s AND transaction_date >= %(to)s::timestamp - interval '90 days' AND transaction_date < %(to)s::timestamp ORDER BY transaction_date DESC LIMIT 50
```

| Variante | Tiempo de ejecución | Acceso |
|---|---|---|
| índices actuales | 0.011 ms | ix_transactions_customer_id_transaction_date |
| sin `ix_transactions_customer_id_transaction_date` | 96.909 ms | Seq Scan |

<details><summary>Plan: índices actuales</summary>

```
Limit (actual time=0.005..0.008 rows=8 loops=1)
  Buffers: shared hit=12
  ->  Index Scan using ix_transactions_customer_id_transaction_date on transactions (actual time=0.005..0.007 rows=8 loops=1)
        Index Cond: (((customer_id)::text = '<cid>'::text) AND (transaction_date >= '2026-03-14 06:19:29'::timestamp without time zone) AND (transaction_date < '<to>'::timestamp without time zone))
        Buffers: shared hit=12
Planning Time: 0.018 ms
Execution Time: 0.011 ms
```
</details>

<details><summary>Plan: sin `ix_transactions_customer_id_transaction_date`</summary>

```
Limit (actual time=95.265..96.734 rows=8 loops=1)
  Buffers: shared hit=3267 read=150069
  ->  Gather Merge (actual time=93.297..94.766 rows=8 loops=1)
        Workers Planned: 2
        Workers Launched: 2
        Buffers: shared hit=3267 read=150069
        ->  Sort (actual time=88.684..88.685 rows=3 loops=3)
              Sort Key: transaction_date DESC
              Sort Method: quicksort  Memory: 25kB
              Buffers: shared hit=3267 read=150069
              Worker 0:  Sort Method: quicksort  Memory: 25kB
              Worker 1:  Sort Method: quicksort  Memory: 25kB
              ->  Parallel Seq Scan on transactions (actual time=9.735..88.643 rows=3 loops=3)
                    Filter: ((transaction_date >= '2026-03-14 06:19:29'::timestamp without time zone) AND (transaction_date < '<to>'::timestamp without time zone) AND ((customer_id)::text = '<cid>'::text))
                    Rows Removed by Filter: 1475000
                    Buffers: shared hit=3155 read=150069
Planning Time: 0.049 ms
Execution Time: 96.909 ms
```
</details>

## `ix_transactions_customer_id_amount (eliminado en 0002)`

Consulta: search_transactions con monto: candidatas a ±10 % del monto dicho.

```sql
SELECT transaction_id, transaction_date, amount, currency FROM ref.transactions WHERE customer_id = %(cid)s AND amount BETWEEN %(amt)s * 0.9 AND %(amt)s * 1.1
```

| Variante | Tiempo de ejecución | Acceso |
|---|---|---|
| índices actuales (sirve el de fecha) | 0.054 ms | ix_transactions_customer_id_transaction_date |
| con `ix_transactions_customer_id_amount` (creado temporalmente) | 0.009 ms | ix_transactions_customer_id_amount |
| sin ningún índice por customer_id | 157.214 ms | Seq Scan |

<details><summary>Plan: índices actuales (sirve el de fecha)</summary>

```
Bitmap Heap Scan on transactions (actual time=0.017..0.050 rows=9 loops=1)
  Recheck Cond: ((customer_id)::text = '<cid>'::text)
  Filter: ((amount >= 290.574) AND (amount <= 355.146))
  Rows Removed by Filter: 141
  Heap Blocks: exact=150
  Buffers: shared hit=154
  ->  Bitmap Index Scan on ix_transactions_customer_id_transaction_date (actual time=0.008..0.008 rows=150 loops=1)
        Index Cond: ((customer_id)::text = '<cid>'::text)
        Buffers: shared hit=4
Planning Time: 0.021 ms
Execution Time: 0.054 ms
```
</details>

<details><summary>Plan: con `ix_transactions_customer_id_amount` (creado temporalmente)</summary>

```
Index Scan using ix_transactions_customer_id_amount on transactions (actual time=0.004..0.007 rows=9 loops=1)
  Index Cond: (((customer_id)::text = '<cid>'::text) AND (amount >= 290.574) AND (amount <= 355.146))
  Buffers: shared hit=13
Planning Time: 0.018 ms
Execution Time: 0.009 ms
```
</details>

<details><summary>Plan: sin ningún índice por customer_id</summary>

```
Gather (actual time=4.542..157.085 rows=9 loops=1)
  Workers Planned: 2
  Workers Launched: 2
  Buffers: shared hit=3443 read=149781
  ->  Parallel Seq Scan on transactions (actual time=47.429..150.527 rows=3 loops=3)
        Filter: ((amount >= 290.574) AND (amount <= 355.146) AND ((customer_id)::text = '<cid>'::text))
        Rows Removed by Filter: 1475000
        Buffers: shared hit=3443 read=149781
Planning Time: 0.043 ms
Execution Time: 157.214 ms
```
</details>

## `ix_transactions_product_id`

Consulta: historial de una tarjeta (contexto de lock_card) y soporte de la FK a products.

```sql
SELECT transaction_id, transaction_date, amount FROM ref.transactions WHERE product_id = %(pid)s ORDER BY transaction_date DESC LIMIT 20
```

| Variante | Tiempo de ejecución | Acceso |
|---|---|---|
| índices actuales | 0.015 ms | ix_transactions_product_id |
| sin `ix_transactions_product_id` | 92.024 ms | Seq Scan |

<details><summary>Plan: índices actuales</summary>

```
Limit (actual time=0.010..0.011 rows=20 loops=1)
  Buffers: shared hit=25
  ->  Sort (actual time=0.010..0.011 rows=20 loops=1)
        Sort Key: transaction_date DESC
        Sort Method: quicksort  Memory: 26kB
        Buffers: shared hit=25
        ->  Index Scan using ix_transactions_product_id on transactions (actual time=0.004..0.008 rows=22 loops=1)
              Index Cond: ((product_id)::text = '<pid>'::text)
              Buffers: shared hit=25
Planning Time: 0.012 ms
Execution Time: 0.015 ms
```
</details>

<details><summary>Plan: sin `ix_transactions_product_id`</summary>

```
Limit (actual time=90.372..91.856 rows=20 loops=1)
  Buffers: shared hit=3747 read=149589
  ->  Gather Merge (actual time=89.039..90.521 rows=20 loops=1)
        Workers Planned: 2
        Workers Launched: 2
        Buffers: shared hit=3747 read=149589
        ->  Sort (actual time=84.303..84.303 rows=7 loops=3)
              Sort Key: transaction_date DESC
              Sort Method: quicksort  Memory: 25kB
              Buffers: shared hit=3747 read=149589
              Worker 0:  Sort Method: quicksort  Memory: 25kB
              Worker 1:  Sort Method: quicksort  Memory: 25kB
              ->  Parallel Seq Scan on transactions (actual time=17.332..84.264 rows=7 loops=3)
                    Filter: ((product_id)::text = '<pid>'::text)
                    Rows Removed by Filter: 1474995
                    Buffers: shared hit=3635 read=149589
Planning Time: 0.045 ms
Execution Time: 92.024 ms
```
</details>

## `ix_transactions_process_date`

Consulta: carga incremental: borrar una partición (un día) antes de recargarla.

```sql
DELETE FROM ref.transactions WHERE process_date = %(pd)s
```

| Variante | Tiempo de ejecución | Acceso |
|---|---|---|
| índices actuales | 1.063 ms | ix_transactions_process_date |
| sin `ix_transactions_process_date` | 179.512 ms | Seq Scan |

<details><summary>Plan: índices actuales</summary>

```
Delete on transactions (actual time=1.059..1.059 rows=0 loops=1)
  Buffers: shared hit=5612
  ->  Bitmap Heap Scan on transactions (actual time=0.056..0.454 rows=5268 loops=1)
        Recheck Cond: (process_date = '<pd>'::date)
        Heap Blocks: exact=337
        Buffers: shared hit=344
        ->  Bitmap Index Scan on ix_transactions_process_date (actual time=0.042..0.042 rows=5268 loops=1)
              Index Cond: (process_date = '<pd>'::date)
              Buffers: shared hit=7
Planning Time: 0.019 ms
Execution Time: 1.063 ms
```
</details>

<details><summary>Plan: sin `ix_transactions_process_date`</summary>

```
Delete on transactions (actual time=179.384..179.385 rows=0 loops=1)
  Buffers: shared hit=9347 read=149145
  ->  Seq Scan on transactions (actual time=19.564..178.686 rows=5268 loops=1)
        Filter: (process_date = '<pd>'::date)
        Rows Removed by Filter: 4419740
        Buffers: shared hit=4079 read=149145
Planning Time: 0.036 ms
Execution Time: 179.512 ms
```
</details>

## `ix_products_customer_id`

Consulta: productos/tarjetas del cliente (get_card_status, lock_card).

```sql
SELECT product_id, product_type, product_status FROM ref.products WHERE customer_id = %(cid)s
```

| Variante | Tiempo de ejecución | Acceso |
|---|---|---|
| índices actuales | 0.012 ms | ix_products_customer_id |
| sin `ix_products_customer_id` | 12.122 ms | Seq Scan |

<details><summary>Plan: índices actuales</summary>

```
Bitmap Heap Scan on products (actual time=0.006..0.010 rows=10 loops=1)
  Recheck Cond: ((customer_id)::text = '<cid>'::text)
  Heap Blocks: exact=10
  Buffers: shared hit=13
  ->  Bitmap Index Scan on ix_products_customer_id (actual time=0.004..0.004 rows=10 loops=1)
        Index Cond: ((customer_id)::text = '<cid>'::text)
        Buffers: shared hit=3
Planning Time: 0.012 ms
Execution Time: 0.012 ms
```
</details>

<details><summary>Plan: sin `ix_products_customer_id`</summary>

```
Gather (actual time=0.356..12.116 rows=10 loops=1)
  Workers Planned: 2
  Workers Launched: 2
  Buffers: shared hit=9672
  ->  Parallel Seq Scan on products (actual time=1.651..6.639 rows=3 loops=3)
        Filter: ((customer_id)::text = '<cid>'::text)
        Rows Removed by Filter: 133330
        Buffers: shared hit=9672
Planning Time: 0.029 ms
Execution Time: 12.122 ms
```
</details>
