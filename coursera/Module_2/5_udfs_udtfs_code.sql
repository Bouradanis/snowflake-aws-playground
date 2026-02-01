---> here’s an example of a function in action!
SELECT ABS(-14);

---> here’s another example of a function in action!
SELECT UPPER('upper');

---> see all functions
SHOW FUNCTIONS;

SELECT MAX(SALE_PRICE_USD) FROM TASTY_BYTES.RAW_POS.MENU;

---> use a particular database
USE DATABASE TASTY_BYTES;

---> create the max_menu_price function
CREATE FUNCTION max_menu_price()
  RETURNS NUMBER(5,2)
  AS
  $$
    SELECT MAX(SALE_PRICE_USD) FROM TASTY_BYTES.RAW_POS.MENU
  $$
  ;

---> run the max_menu_price function by calling it in a select statement
SELECT max_menu_price();

SHOW FUNCTIONS;

---> create a new function, but one that takes in an argument
CREATE FUNCTION max_menu_price_converted(USD_to_new NUMBER)
  RETURNS NUMBER(5,2)
  AS
  $$
    SELECT USD_TO_NEW*MAX(SALE_PRICE_USD) FROM TASTY_BYTES.RAW_POS.MENU
  $$
  ;

SELECT max_menu_price_converted(1.35);

---> create a Python function
CREATE FUNCTION winsorize (val NUMERIC, up_bound NUMERIC, low_bound NUMERIC)
returns NUMERIC
language python
runtime_version = '3.11'
handler = 'winsorize_py'
AS
$$
def winsorize_py(val, up_bound, low_bound):
    if val > up_bound:
        return up_bound
    elif val < low_bound:
        return low_bound
    else:
        return val
$$;

---> run the Python function
SELECT winsorize(12.0, 11.0, 4.0);

---> here’s the reference UDF we’re going to work off of as we make our UDTF
CREATE FUNCTION max_menu_price()
  RETURNS NUMBER(5,2)
  AS
  $$
    SELECT MAX(SALE_PRICE_USD) FROM TASTY_BYTES.RAW_POS.MENU
  $$
  ;

USE DATABASE TASTY_BYTES;

---> create a user-defined table function
CREATE FUNCTION menu_prices_above(price_floor NUMBER)
  RETURNS TABLE (item VARCHAR, price NUMBER)
  AS
  $$
    SELECT MENU_ITEM_NAME, SALE_PRICE_USD
    FROM TASTY_BYTES.RAW_POS.MENU
    WHERE SALE_PRICE_USD > price_floor
    ORDER BY 2 DESC
  $$
  ;

---> now you can see it in the list of all functions!
SHOW FUNCTIONS;

---> run the UDTF to see what the output looks like
SELECT * FROM TABLE(menu_prices_above(15));

---> you can use a where clause on the result
SELECT * FROM TABLE(menu_prices_above(15))
WHERE ITEM ILIKE '%CHICKEN%';