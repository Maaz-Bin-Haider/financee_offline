"""Installation currency presentation only; never converts or recalculates money."""
import re

def currency_config(profile):
    if profile is None: return {'code':'', 'symbol':'', 'label':''}
    return {'code':profile.base_currency_id, 'symbol':profile.currency_symbol,
            'label':profile.symbol_override or profile.base_currency_id}

def present_dashboard_alerts(alerts, profile):
    """Localize only known generated labels, retaining the SQL's exact amount text.
    Titles may contain customer names; never replace words in those fields.
    """
    label = currency_config(profile)['label']
    pattern = r'^(Cash balance is |Balance |High receivable )PKR (?=[+-]?\d)'
    return [dict(alert, message=re.sub(pattern, lambda m:m[1]+label+' ', alert.get('message','')))
            for alert in alerts]
