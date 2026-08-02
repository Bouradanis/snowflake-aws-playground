

SELECT SNOWFLAKE.CORTEX.COMPLETE(
    'mistral-7b', 'What kind of literature was Marianne Moore known for?');

SELECT SNOWFLAKE.CORTEX.COMPLETE(
    'mistral-7b',
        CONCAT('Describe this food: ', menu_item_name)
) FROM TASTY_BYTES.RAW_POS.MENU LIMIT 5;