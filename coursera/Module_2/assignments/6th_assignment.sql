create role tasty_role;

show grants;

show grants to role tasty_role;

GRANT CREATE DATABASE ON ACCOUNT TO ROLE tasty_role;

SHOW GRANTS;

select current_user;

grant role tasty_role to user abourantanis;

use role tasty_role;

drop warehouse tasty_test_wh;

create warehouse tasty_test_wh;

show warehouses;

use role accountadmin;

show grants to user abourantanis;

show grants to role USERADMIN;
