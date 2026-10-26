from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import get_user_model
from .models import Currency, GeneralSettings

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


class GeneralSettingsForm(forms.ModelForm):
    enabled_modules = forms.MultipleChoiceField(required=False, widget=forms.CheckboxSelectMultiple,
        label='Available modules', help_text='Local availability only. User permissions still control access. Disabling drafts does not release reserved stock. Dark mode always stays available.')
    timezone = forms.ChoiceField(label='Timezone')
    class Meta:
        model = GeneralSettings
        fields = ('name','base_currency','symbol_override','timezone','contact_email','phone','address')
        widgets = {'address':forms.Textarea(attrs={'rows':3})}
        help_texts = {
            'base_currency':'The accounting currency. Change it only before any financial posting; no FX conversion is performed.',
            'symbol_override':'Optional cosmetic prefix, such as Dhs or €. Leave blank to use the currency code in amounts. Stored amounts and base currency do not change.',
            'contact_email':'Printed company contact only; Financee does not send email.',
        }
    def __init__(self,*args,**kwargs):
        from zoneinfo import available_timezones
        from .features import FEATURE_GROUPS
        super().__init__(*args,**kwargs)
        self.fields['timezone'].choices=[(zone,zone) for zone in sorted(available_timezones())]
        if 'base_currency' in self.fields:self.fields['base_currency'].queryset=Currency.objects.filter(is_active=True)
        self.fields['enabled_modules'].choices=[(key,entry['label']) for key,entry in FEATURE_GROUPS.items()]
        self.fields['enabled_modules'].initial=[key for key in FEATURE_GROUPS if key not in (self.instance.disabled_features or [])]
    def save(self,commit=True):
        from .features import FEATURE_GROUPS
        obj=super().save(commit=False)
        enabled=set(self.cleaned_data['enabled_modules'])
        obj.disabled_features=[key for key in FEATURE_GROUPS if key not in enabled]
        if commit:obj.save()
        return obj
