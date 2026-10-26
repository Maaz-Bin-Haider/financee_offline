from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import get_user_model
from .models import Currency

class SetupForm(UserCreationForm):
    company_name = forms.CharField(max_length=150, label='Company name')
    currency = forms.ModelChoiceField(queryset=Currency.objects.filter(is_active=True))
    symbol_override = forms.CharField(max_length=12, required=False, label='Display symbol override (optional)')
    timezone = forms.CharField(initial='Asia/Karachi', max_length=64, label='Timezone (IANA name)')
    class Meta(UserCreationForm.Meta):
        model = get_user_model()
        fields = ('company_name','currency','symbol_override','timezone','username','password1','password2')
    def clean_timezone(self):
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
        value = self.cleaned_data['timezone']
        try: ZoneInfo(value)
        except (ValueError, ZoneInfoNotFoundError): raise forms.ValidationError('Choose a valid IANA timezone.')
        return value
