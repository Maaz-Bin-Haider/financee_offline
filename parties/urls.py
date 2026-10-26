from django.urls import path

from .views import create_new_party, update_party,auto_complete_party,parties_hub,parties_list_json

app_name = "parties" 

urlpatterns = [
    path('parties-dash/', parties_hub, name='partiesDash'),  
    path('add-new-party/',create_new_party,name='add_new_party'),
    path('update-party/',update_party,name='update_party'),
    path('autocomplete-party',auto_complete_party,name='autocomplete_party'),
    path('parties-list/', parties_list_json, name='parties_list'),
]