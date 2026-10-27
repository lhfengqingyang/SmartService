INSERT INTO biz.orders (id, user_id, status, total_amount, created_at, delivered_at)
VALUES
    ('demo-refundable', 'demo-user', 'completed', 199.00, now() - interval '5 days', now() - interval '2 days'),
    ('demo-expired', 'demo-user', 'completed', 88.00, now() - interval '20 days', now() - interval '10 days'),
    ('demo-shipped', 'demo-user', 'shipped', 59.90, now() - interval '1 day', NULL)
ON CONFLICT (id) DO NOTHING;

INSERT INTO biz.order_items (order_id, product_name, quantity, price)
SELECT 'demo-refundable', 'SmartService 演示耳机', 1, 199.00
WHERE NOT EXISTS (SELECT 1 FROM biz.order_items WHERE order_id = 'demo-refundable');

INSERT INTO biz.order_items (order_id, product_name, quantity, price)
SELECT 'demo-expired', 'SmartService 演示键盘', 1, 88.00
WHERE NOT EXISTS (SELECT 1 FROM biz.order_items WHERE order_id = 'demo-expired');

INSERT INTO biz.order_items (order_id, product_name, quantity, price)
SELECT 'demo-shipped', 'SmartService 演示鼠标', 1, 59.90
WHERE NOT EXISTS (SELECT 1 FROM biz.order_items WHERE order_id = 'demo-shipped');
