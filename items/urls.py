from django.urls import path

from .views import create_new_item,update_item_view,autocomplete_item,items_hub,items_list_json

app_name = "items"

urlpatterns = [
    path('items-dash/', items_hub, name='itemsDash'),
    path('add-new-item/',create_new_item,name='add_new_item'),
    path('update-item/',update_item_view,name='update_item'),
    path('autocomplete-item/', autocomplete_item, name='autocomplete_item'),
    path('items-list/', items_list_json, name='items_list'),
]
