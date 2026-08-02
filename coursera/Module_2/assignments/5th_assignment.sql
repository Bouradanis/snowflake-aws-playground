use warehouse compute_wh;

use schema RAW_POS;

select * from menu m
limit 5;


use database tasty_bytes_clone;

use schema RAW_POS;


create procedure tasty_bytes_clone.raw_pos.increase_prices()
returns boolean
language sql
as
$$
BEGIN
UPDATE tasty_bytes_clone.raw_pos.menu
SET SALE_PRICE_USD = menu.SALE_PRICE_USD + 1;
END;
$$;

show procedures;

CALL INCREASE_PRICES();

describe procedure increase_prices();

select * from tasty_bytes_clone.raw_pos.menu
limit 10;


create procedure tasty_bytes_clone.raw_pos.decrease_mango_sticky_rice_price()
returns boolean
language sql
as
$$
begin
update tasty_bytes_clone.raw_pos.menu m
set m.SALE_PRICE_USD= m.SALE_PRICE_USD-1
where m.MENU_ITEM_NAME = 'Mango Sticky Rice';
end;
$$;

show procedures;





