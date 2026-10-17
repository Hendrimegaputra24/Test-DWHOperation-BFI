{% macro generate_schema_name(custom_schema_name, node) -%}
    {#- Pakai nama schema persis (silver / gold), tanpa awalan schema bawaan. -#}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
