{#- Dimensi tanggal (kalender) 2026-2027. Nama hari dan bulan dalam bahasa Indonesia. -#}
with d as (
    select generate_series('2026-01-01'::date, '2027-12-31'::date, interval '1 day')::date as date_day
)
select
    to_char(date_day, 'YYYYMMDD')::int                                         as date_key,
    date_day                                                                   as date,
    extract(year from date_day)::int                                           as year,
    extract(quarter from date_day)::int                                        as quarter,
    extract(month from date_day)::int                                          as month,
    (array['Januari','Februari','Maret','April','Mei','Juni','Juli','Agustus',
           'September','Oktober','November','Desember'])[extract(month from date_day)::int] as month_name,
    extract(week from date_day)::int                                           as iso_week,
    extract(isodow from date_day)::int                                         as day_of_week,
    (array['Senin','Selasa','Rabu','Kamis','Jumat','Sabtu','Minggu'])[extract(isodow from date_day)::int] as day_name,
    extract(isodow from date_day) in (6, 7)                                    as is_weekend
from d
