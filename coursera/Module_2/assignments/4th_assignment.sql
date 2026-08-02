show schemas;

show functions;

show functions like '%timestamp%';

create function TASTY_BYTES.RAW_POS.min_menu_price()
    returns number(5,2)
AS
    $$
    select min(m.SALE_PRICE_USD)
    from tasty_bytes.raw_pos.menu m
    $$;

SELECT min_menu_price();

show functions like '%min_menu_price%';

create function tasty_bytes.raw_pos.menu_prices_below(
    price_ceiling number
)
    returns table(
        item varchar,
        price number
            )
AS
    $$
    SELECT MENU_ITEM_NAME, SALE_PRICE_USD
    FROM TASTY_BYTES.RAW_POS.MENU
    WHERE SALE_PRICE_USD < price_ceiling
    ORDER BY 2 DESC
    $$;

SELECT * FROM TABLE(menu_prices_below(3));