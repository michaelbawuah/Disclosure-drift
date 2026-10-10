SELECT
    crsp_a_stock.wrds_names_query.permno,
    crsp_a_stock.wrds_names_query.hdrprimaryexch,
    crsp_a_stock.wrds_names_query.nasdissuno,
    crsp_a_stock.wrds_names_query.hdrsiccd,
    crsp_a_stock.wrds_names_query.permco,
    crsp_a_stock.wrds_names_query.secinfostartdt,
    crsp_a_stock.wrds_names_query.secinfoenddt,
    crsp_a_stock.wrds_names_query.securitybegdt,
    crsp_a_stock.wrds_names_query.securityenddt,
    crsp_a_stock.wrds_names_query.cusip,
    crsp_a_stock.wrds_names_query.ticker,
    crsp_a_stock.wrds_names_query.issuernm,
    crsp_a_stock.wrds_names_query.shareclass,
    crsp_a_stock.wrds_names_query.usincflg,
    crsp_a_stock.wrds_names_query.issuertype,
    crsp_a_stock.wrds_names_query.securitytype,
    crsp_a_stock.wrds_names_query.securitysubtype,
    crsp_a_stock.wrds_names_query.sharetype,
    crsp_a_stock.wrds_names_query.securityactiveflg,
    crsp_a_stock.wrds_names_query.siccd,
    crsp_a_stock.wrds_names_query.primaryexch,
    crsp_a_stock.wrds_names_query.tradingsymbol,
    crsp_a_stock.wrds_names_query.naics,
    crsp_a_stock.wrds_names_query.tradingstatusflg

FROM crsp_a_stock.wrds_names_query
INNER JOIN (
    SELECT DISTINCT crsp_a_stock.wrds_names_query.permno
    FROM crsp_a_stock.wrds_names_query
    WHERE crsp_a_stock.wrds_names_query.permno IN (
        '10107',
        '11308',
        '11850',
        '12060',
        '12490',
        '13856',
        '14593',
        '18163',
        '18542',
        '22111',
        '26403',
        '47896',
        '55976',
        '59328',
        '59408',
        '66181',
        '76076',
        '84788',
        '86580',
        '92655'
    )
) AS id_table 

ON crsp_a_stock.wrds_names_query.permno = id_table.permno

WHERE 1 = 1
