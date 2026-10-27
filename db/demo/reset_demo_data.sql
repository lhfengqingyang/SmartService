BEGIN;

DELETE FROM biz.refund_applications
WHERE order_id IN ('demo-refundable', 'demo-expired', 'demo-shipped');

DELETE FROM biz.order_items
WHERE order_id IN ('demo-refundable', 'demo-expired', 'demo-shipped');

DELETE FROM biz.orders
WHERE id IN ('demo-refundable', 'demo-expired', 'demo-shipped');

INSERT INTO biz.orders (id, user_id, status, total_amount, created_at, delivered_at)
VALUES
    ('demo-refundable', 'demo-user', 'completed', 199.00, now() - interval '5 days', now() - interval '2 days'),
    ('demo-expired', 'demo-user', 'completed', 88.00, now() - interval '20 days', now() - interval '10 days'),
    ('demo-shipped', 'demo-user', 'shipped', 59.90, now() - interval '1 day', NULL);

INSERT INTO biz.order_items (order_id, product_name, quantity, price)
VALUES
    ('demo-refundable', 'SmartService 演示耳机', 1, 199.00),
    ('demo-expired', 'SmartService 演示键盘', 1, 88.00),
    ('demo-shipped', 'SmartService 演示鼠标', 1, 59.90);

COMMIT;
