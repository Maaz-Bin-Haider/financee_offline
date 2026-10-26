import hashlib

def verify(actual,contract):
    values={name:dict(body_sha256=hashlib.sha256(body.encode()).hexdigest(),result=result,volatility=volatility,strict=strict,security_definer=security) for name,(body,result,volatility,strict,security) in actual.items()}
    expected=contract['functions']
    if not all(values.get(k)==v for k,v in expected.items()):raise ValueError('Financial SQL differs from the confirmed source contract.')
    if sorted(set(values)-set(expected))!=['local_currency_posting_lock()','local_profile_guard()','local_profile_no_truncate()']:raise ValueError('Unexpected SQL functions.')
