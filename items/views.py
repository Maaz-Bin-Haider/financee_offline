from activity.recorder import record as record_activity
# from django.shortcuts import render,redirect
# from django.db import connection,IntegrityError
# from django.contrib import messages
# from django.http import JsonResponse
# from django.contrib import messages
# import json
# from django.contrib.auth.decorators import login_required

# @login_required
# def create_new_item(request):
#     if not request.user.has_perm("auth.view_item"):
#         messages.error(request, "You do not have permission to Add New Items!")
#         return redirect("home:home")
    
#     if request.method == 'POST':
#         item_name = request.POST.get('item_name')
#         sale_price = request.POST.get('sale_price')
#         storage = request.POST.get('storage')
#         item_code = request.POST.get('item_code')
#         category = request.POST.get('category')
#         brand = request.POST.get('brand')

#         with connection.cursor() as cursor:
#             cursor.execute("SELECT 1 FROM Items WHERE UPPER(item_name) = %s", [item_name.upper()])
#             exists = cursor.fetchone()

#             if exists:
#                 return JsonResponse({
#                     "status": "error",
#                     "message": f"Item with the name '{item_name}' already exists!"
#                 })

#             # Prepare JSON data for function
#             item_data = {
#                 "item_name": item_name.upper(),
#                 "storage": storage,
#                 "sale_price": float(sale_price or 0),
#                 "item_code": item_code,
#                 "category": category,
#                 "brand": brand
#             }

#             json_data = json.dumps(item_data)

#             try:
#                 if request.user.groups.filter(name="view_only_users").exists():
#                     return JsonResponse({
#                         "status": "error",
#                         "message": "You do not have permission to create items."
#                     })
                
#                 #  Access check for Create items Right
#                 if not request.user.has_perm("auth.create_item"):
#                     return JsonResponse({
#                         "status": "error",
#                         "message": "You do not have permission to Add New Items!"
#                     })

#                 cursor.execute("SELECT add_item_from_json(%s)", [json_data])
#                 return JsonResponse({
#                     "status": "success",
#                     "message": f"Item '{item_name}' added successfully!"
#                 })
#             except IntegrityError:
#                 return JsonResponse({
#                     "status": "error",
#                     "message": f"Item '{item_name}' already exists!"
#                 })

#     return render(request, "items_templates/add_new_item.html")




# @login_required
# def get_item_by_name(item_name):

#     with connection.cursor() as cursor:
#         cursor.execute("SELECT get_item_by_name(%s)",[item_name.upper()])
#         row = cursor.fetchone()

#     if row and row[0]:
#         data =  json.loads(row[0])
#         return data[0] if data else None

#     return None


# @login_required
# def update_item_view(request):
#     context = {}

#     # Case 1: Search form submitted
#     if request.method == "GET" and "search_name" in request.GET:
#         search_name = request.GET.get("search_name")
#         item = get_item_by_name(search_name)
#         if item:
#             context["item"] = item
#         else:
#             context["not_found"] = True
        


#     if request.method == 'POST':
#         item_id = request.POST.get("item_id")
#         data = {
#             "item_name": request.POST.get("item_name").upper(),
#             "sale_price": float(request.POST.get("sale_price") or 0),
#             "storage": request.POST.get("storage"),
#             "item_code": request.POST.get("item_code"),
#             "category": request.POST.get("category"),
#             "brand": request.POST.get("brand"),
#         }

#         if item_id:
#             data["item_id"] = int(item_id) 

#         json_data = json.dumps(data)

#         with connection.cursor() as cursor:
#             if item_id:

#                 try:
#                     if request.user.groups.filter(name="view_only_users").exists():
#                         return JsonResponse({
#                             "status": "error",
#                             "message": "You do not have permission to update items."
#                         })
#                     cursor.execute("SELECT update_item_from_json(%s)",[json_data])
#                     messages.success(request, f"Item '{data['item_name']}' Updated successfully!")
#                 except Exception as e:
#                     messages.error(request, f"An Unexpected Error Occured! {e}")
#             else: # means adding new item

#                 try:
#                     if request.user.groups.filter(name="view_only_users").exists():
#                         return JsonResponse({
#                             "status": "error",
#                             "message": "You do not have permission to create items."
#                         })
#                     cursor.execute("SELECT add_item_from_json(%s)",[json_data])
#                     messages.success(request, f"Item '{data['item_name']}' Added successfully!")
#                 except IntegrityError:
#                     messages.error(request, f"Item '{data['item_name']}' already exists!")


#     return render(request, "items_templates/update_item.html",context)


# @login_required
# def autocomplete_item(request):
#     if 'term' in request.GET:
#         term = request.GET.get('term').upper()
#         with connection.cursor() as cursor:
#             cursor.execute("SELECT item_name FROM Items WHERE UPPER(item_name) LIKE %s LIMIT 10", [term + '%'])
#             rows = cursor.fetchall()
#         suggestions = [row[0] for row in rows]
#         return JsonResponse(suggestions, safe=False)
#     return JsonResponse([], safe=False)


# from django.shortcuts import render,redirect
# from django.db import connection,IntegrityError
# from django.contrib import messages
# from django.http import JsonResponse
# from django.contrib import messages
# import json
# from django.contrib.auth.decorators import login_required

# @login_required
# def create_new_item(request):
#     if not request.user.has_perm("auth.view_item"):
#         messages.error(request, "You do not have permission to Add New Items!")
#         return redirect("home:home")
    
#     if request.method == 'POST':
#         item_name = request.POST.get('item_name')
#         sale_price = request.POST.get('sale_price')
#         storage = request.POST.get('storage')
#         item_code = request.POST.get('item_code')
#         category = request.POST.get('category')
#         brand = request.POST.get('brand')

#         with connection.cursor() as cursor:
#             cursor.execute("SELECT 1 FROM Items WHERE UPPER(item_name) = %s", [item_name.upper()])
#             exists = cursor.fetchone()

#             if exists:
#                 return JsonResponse({
#                     "status": "error",
#                     "message": f"Item with the name '{item_name}' already exists!"
#                 })

#             # Prepare JSON data for function
#             item_data = {
#                 "item_name": item_name.upper(),
#                 "storage": storage,
#                 "sale_price": float(sale_price or 0),
#                 "item_code": item_code,
#                 "category": category,
#                 "brand": brand,
#                 "created_by_id": request.user.id       # <-- added
#             }

#             json_data = json.dumps(item_data)

#             try:
#                 if request.user.groups.filter(name="view_only_users").exists():
#                     return JsonResponse({
#                         "status": "error",
#                         "message": "You do not have permission to create items."
#                     })
                
#                 #  Access check for Create items Right
#                 if not request.user.has_perm("auth.create_item"):
#                     return JsonResponse({
#                         "status": "error",
#                         "message": "You do not have permission to Add New Items!"
#                     })

#                 cursor.execute("SELECT add_item_from_json(%s)", [json_data])
#                 return JsonResponse({
#                     "status": "success",
#                     "message": f"Item '{item_name}' added successfully!"
#                 })
#             except IntegrityError:
#                 return JsonResponse({
#                     "status": "error",
#                     "message": f"Item '{item_name}' already exists!"
#                 })

#     return render(request, "items_templates/add_new_item.html")




# @login_required
# def get_item_by_name(item_name):

#     with connection.cursor() as cursor:
#         cursor.execute("SELECT get_item_by_name(%s)",[item_name.upper()])
#         row = cursor.fetchone()

#     if row and row[0]:
#         data =  json.loads(row[0])
#         return data[0] if data else None

#     return None


# @login_required
# def update_item_view(request):
#     context = {}

#     # Case 1: Search form submitted
#     if request.method == "GET" and "search_name" in request.GET:
#         search_name = request.GET.get("search_name")
#         item = get_item_by_name(search_name)
#         if item:
#             context["item"] = item
#         else:
#             context["not_found"] = True
        


#     if request.method == 'POST':
#         item_id = request.POST.get("item_id")
#         data = {
#             "item_name": request.POST.get("item_name").upper(),
#             "sale_price": float(request.POST.get("sale_price") or 0),
#             "storage": request.POST.get("storage"),
#             "item_code": request.POST.get("item_code"),
#             "category": request.POST.get("category"),
#             "brand": request.POST.get("brand"),
#         }

#         if item_id:
#             data["item_id"] = int(item_id) 

#         json_data = json.dumps(data)

#         with connection.cursor() as cursor:
#             if item_id:

#                 try:
#                     if request.user.groups.filter(name="view_only_users").exists():
#                         return JsonResponse({
#                             "status": "error",
#                             "message": "You do not have permission to update items."
#                         })
#                     cursor.execute("SELECT update_item_from_json(%s)",[json_data])
#                     messages.success(request, f"Item '{data['item_name']}' Updated successfully!")
#                 except Exception as e:
#                     messages.error(request, f"An Unexpected Error Occured! {e}")
#             else: # means adding new item

#                 try:
#                     if request.user.groups.filter(name="view_only_users").exists():
#                         return JsonResponse({
#                             "status": "error",
#                             "message": "You do not have permission to create items."
#                         })
#                     data["created_by_id"] = request.user.id
#                     json_data_only_for_add = json.dumps(data)
#                     cursor.execute("SELECT add_item_from_json(%s)",[json_data_only_for_add])
#                     messages.success(request, f"Item '{data['item_name']}' Added successfully!")
#                 except IntegrityError:
#                     messages.error(request, f"Item '{data['item_name']}' already exists!")


#     return render(request, "items_templates/update_item.html",context)


# @login_required
# def autocomplete_item(request):
#     if 'term' in request.GET:
#         term = request.GET.get('term').upper()
#         with connection.cursor() as cursor:
#             cursor.execute("SELECT item_name FROM Items WHERE UPPER(item_name) LIKE %s ORDER BY CASE WHEN UPPER(item_name) LIKE %s THEN 0 ELSE 1 END, item_name LIMIT 10", ['%' + term + '%', term + '%'])
#             rows = cursor.fetchall()
#         suggestions = [row[0] for row in rows]
#         return JsonResponse(suggestions, safe=False)
#     return JsonResponse([], safe=False)


# from django.shortcuts import render,redirect
# from django.db import connection,IntegrityError
# from django.contrib import messages
# from django.http import JsonResponse
# from django.contrib import messages
# import json
# from django.contrib.auth.decorators import login_required

# @login_required
# def create_new_item(request):
#     if not request.user.has_perm("auth.view_item"):
#         messages.error(request, "You do not have permission to Add New Items!")
#         return redirect("home:home")
    
#     if request.method == 'POST':
#         item_name = request.POST.get('item_name')
#         sale_price = request.POST.get('sale_price')
#         storage = request.POST.get('storage')
#         item_code = request.POST.get('item_code')
#         category = request.POST.get('category')
#         brand = request.POST.get('brand')

#         with connection.cursor() as cursor:
#             cursor.execute("SELECT 1 FROM Items WHERE UPPER(item_name) = %s", [item_name.upper()])
#             exists = cursor.fetchone()

#             if exists:
#                 return JsonResponse({
#                     "status": "error",
#                     "message": f"Item with the name '{item_name}' already exists!"
#                 })

#             # Prepare JSON data for function
#             item_data = {
#                 "item_name": item_name.upper(),
#                 "storage": storage,
#                 "sale_price": float(sale_price or 0),
#                 "item_code": item_code,
#                 "category": category,
#                 "brand": brand
#             }

#             json_data = json.dumps(item_data)

#             try:
#                 if request.user.groups.filter(name="view_only_users").exists():
#                     return JsonResponse({
#                         "status": "error",
#                         "message": "You do not have permission to create items."
#                     })
                
#                 #  Access check for Create items Right
#                 if not request.user.has_perm("auth.create_item"):
#                     return JsonResponse({
#                         "status": "error",
#                         "message": "You do not have permission to Add New Items!"
#                     })

#                 cursor.execute("SELECT add_item_from_json(%s)", [json_data])
#                 return JsonResponse({
#                     "status": "success",
#                     "message": f"Item '{item_name}' added successfully!"
#                 })
#             except IntegrityError:
#                 return JsonResponse({
#                     "status": "error",
#                     "message": f"Item '{item_name}' already exists!"
#                 })

#     return render(request, "items_templates/add_new_item.html")




# @login_required
# def get_item_by_name(item_name):

#     with connection.cursor() as cursor:
#         cursor.execute("SELECT get_item_by_name(%s)",[item_name.upper()])
#         row = cursor.fetchone()

#     if row and row[0]:
#         data =  json.loads(row[0])
#         return data[0] if data else None

#     return None


# @login_required
# def update_item_view(request):
#     context = {}

#     # Case 1: Search form submitted
#     if request.method == "GET" and "search_name" in request.GET:
#         search_name = request.GET.get("search_name")
#         item = get_item_by_name(search_name)
#         if item:
#             context["item"] = item
#         else:
#             context["not_found"] = True
        


#     if request.method == 'POST':
#         item_id = request.POST.get("item_id")
#         data = {
#             "item_name": request.POST.get("item_name").upper(),
#             "sale_price": float(request.POST.get("sale_price") or 0),
#             "storage": request.POST.get("storage"),
#             "item_code": request.POST.get("item_code"),
#             "category": request.POST.get("category"),
#             "brand": request.POST.get("brand"),
#         }

#         if item_id:
#             data["item_id"] = int(item_id) 

#         json_data = json.dumps(data)

#         with connection.cursor() as cursor:
#             if item_id:

#                 try:
#                     if request.user.groups.filter(name="view_only_users").exists():
#                         return JsonResponse({
#                             "status": "error",
#                             "message": "You do not have permission to update items."
#                         })
#                     cursor.execute("SELECT update_item_from_json(%s)",[json_data])
#                     messages.success(request, f"Item '{data['item_name']}' Updated successfully!")
#                 except Exception as e:
#                     messages.error(request, f"An Unexpected Error Occured! {e}")
#             else: # means adding new item

#                 try:
#                     if request.user.groups.filter(name="view_only_users").exists():
#                         return JsonResponse({
#                             "status": "error",
#                             "message": "You do not have permission to create items."
#                         })
#                     cursor.execute("SELECT add_item_from_json(%s)",[json_data])
#                     messages.success(request, f"Item '{data['item_name']}' Added successfully!")
#                 except IntegrityError:
#                     messages.error(request, f"Item '{data['item_name']}' already exists!")


#     return render(request, "items_templates/update_item.html",context)


# @login_required
# def autocomplete_item(request):
#     if 'term' in request.GET:
#         term = request.GET.get('term').upper()
#         with connection.cursor() as cursor:
#             cursor.execute("SELECT item_name FROM Items WHERE UPPER(item_name) LIKE %s LIMIT 10", [term + '%'])
#             rows = cursor.fetchall()
#         suggestions = [row[0] for row in rows]
#         return JsonResponse(suggestions, safe=False)
#     return JsonResponse([], safe=False)


from django.shortcuts import render,redirect
from django.db import connection,IntegrityError
from django.contrib import messages
from django.http import JsonResponse
from django.contrib import messages
import json
from django.contrib.auth.decorators import login_required

@login_required
def create_new_item(request):
    if not request.user.has_perm("auth.view_item"):
        messages.error(request, "You do not have permission to Add New Items!")
        return redirect("home:home")
    
    if request.method == 'POST':
        item_name = request.POST.get('item_name')
        sale_price = request.POST.get('sale_price')
        storage = request.POST.get('storage')
        item_code = request.POST.get('item_code')
        category = request.POST.get('category')
        brand = request.POST.get('brand')

        # Validate required input before using it (prevents 500 on missing field).
        if not item_name or not item_name.strip():
            return JsonResponse({"status": "error", "message": "Item name is required."})
        item_name = item_name.strip()

        with connection.cursor() as cursor:
            cursor.execute("SELECT 1 FROM Items WHERE UPPER(item_name) = %s", [item_name.upper()])
            exists = cursor.fetchone()

            if exists:
                return JsonResponse({
                    "status": "error",
                    "message": f"Item with the name '{item_name}' already exists!"
                })

            # Prepare JSON data for function
            item_data = {
                "item_name": item_name.upper(),
                "storage": storage,
                "sale_price": float(sale_price or 0),
                "item_code": item_code,
                "category": category,
                "brand": brand,
                "created_by_id": request.user.id
            }

            json_data = json.dumps(item_data)

            try:
                if request.user.groups.filter(name="view_only_users").exists():
                    return JsonResponse({
                        "status": "error",
                        "message": "You do not have permission to create items."
                    })
                
                #  Access check for Create items Right
                if not request.user.has_perm("auth.create_item"):
                    return JsonResponse({
                        "status": "error",
                        "message": "You do not have permission to Add New Items!"
                    })

                cursor.execute("SELECT add_item_from_json(%s)", [json_data])
                return JsonResponse({
                    "status": "success",
                    "message": f"Item '{item_name}' added successfully!"
                })
            except IntegrityError:
                return JsonResponse({
                    "status": "error",
                    "message": f"Item '{item_name}' already exists!"
                })

    return render(request, "items_templates/add_new_item.html")




def get_item_by_name(item_name):
    # NOTE: This is an internal helper (NOT a view). It must not carry the
    # @login_required decorator, otherwise it expects a `request` object and
    # crashes when called with a plain string. Access is already guarded by the
    # calling view (update_item_view), which is @login_required.
    with connection.cursor() as cursor:
        cursor.execute("SELECT get_item_by_name(%s)",[item_name.upper()])
        row = cursor.fetchone()

    if row and row[0]:
        data =  json.loads(row[0])
        return data[0] if data else None

    return None


@login_required
def update_item_view(request):
    context = {}

    # ──────────────────────────────────────────────────────────────────
    # AJAX branch (used by the Items hub / single-page UI).
    # Only triggers for XMLHttpRequest calls so the standalone
    # update_item.html page keeps behaving exactly as before.
    # ──────────────────────────────────────────────────────────────────
    is_ajax = request.headers.get("x-requested-with") == "XMLHttpRequest"

    if is_ajax:
        # --- AJAX search: return the item as JSON ---
        if request.method == "GET" and "search_name" in request.GET:
            item = get_item_by_name(request.GET.get("search_name"))
            if item:
                return JsonResponse({"status": "found", "item": item})
            return JsonResponse({"status": "not_found"})

        # --- AJAX update: apply changes and return JSON ---
        if request.method == "POST":
            item_id = request.POST.get("item_id")
            if not item_id:
                return JsonResponse({
                    "status": "error",
                    "message": "No item selected to update. Please search and select an item first."
                })

            if request.user.groups.filter(name="view_only_users").exists():
                return JsonResponse({
                    "status": "error",
                    "message": "You do not have permission to update items."
                })

            if not request.user.has_perm("auth.update_item"):
                return JsonResponse({
                    "status": "error",
                    "message": "You do not have permission to Update Items!"
                })

            if not (request.POST.get("item_name") or "").strip():
                return JsonResponse({
                    "status": "error",
                    "message": "Item name is required."
                })

            data = {
                "item_id": int(item_id),
                "item_name": (request.POST.get("item_name") or "").strip().upper(),
                "sale_price": float(request.POST.get("sale_price") or 0),
                "storage": request.POST.get("storage"),
                "item_code": request.POST.get("item_code"),
                "category": request.POST.get("category"),
                "brand": request.POST.get("brand"),
                "created_by_id": request.user.id,
            }

            try:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT update_item_from_json(%s)", [json.dumps(data)])
                return JsonResponse({
                    "status": "success",
                    "message": f"Item '{data['item_name']}' updated successfully!"
                })
            except Exception as e:
                return JsonResponse({
                    "status": "error",
                    "message": f"An unexpected error occurred! {e}"
                })

    # ──────────────────────────────────────────────────────────────────
    # Original (non-AJAX) standalone-page behaviour — unchanged.
    # ──────────────────────────────────────────────────────────────────
    # Case 1: Search form submitted
    if request.method == "GET" and "search_name" in request.GET:
        search_name = request.GET.get("search_name")
        item = get_item_by_name(search_name)
        if item:
            context["item"] = item
        else:
            context["not_found"] = True
        


    if request.method == 'POST':
        item_id = request.POST.get("item_id")
        if not (request.POST.get("item_name") or "").strip():
            messages.error(request, "Item name is required.")
            return render(request, "items_templates/update_item.html", context)
        data = {
            "item_name": (request.POST.get("item_name") or "").strip().upper(),
            "sale_price": float(request.POST.get("sale_price") or 0),
            "storage": request.POST.get("storage"),
            "item_code": request.POST.get("item_code"),
            "category": request.POST.get("category"),
            "brand": request.POST.get("brand"),
        }

        if item_id:
            data["item_id"] = int(item_id)

        # Always record who last touched this record
        data["created_by_id"] = request.user.id

        json_data = json.dumps(data)

        with connection.cursor() as cursor:
            if item_id:

                try:
                    if request.user.groups.filter(name="view_only_users").exists():
                        return JsonResponse({
                            "status": "error",
                            "message": "You do not have permission to update items."
                        })
                    cursor.execute("SELECT update_item_from_json(%s)",[json_data])
                    messages.success(request, f"Item '{data['item_name']}' Updated successfully!")
                    record_activity(request, 'update', 'item', item_id, 'Item · update')
                except Exception as e:
                    messages.error(request, f"An Unexpected Error Occured! {e}")
            else: # means adding new item

                try:
                    if request.user.groups.filter(name="view_only_users").exists():
                        return JsonResponse({
                            "status": "error",
                            "message": "You do not have permission to create items."
                        })
                    cursor.execute("SELECT add_item_from_json(%s)",[json_data])
                    messages.success(request, f"Item '{data['item_name']}' Added successfully!")
                    record_activity(request, 'create', 'item', item_id, 'Item · create')
                except IntegrityError:
                    messages.error(request, f"Item '{data['item_name']}' already exists!")


    return render(request, "items_templates/update_item.html",context)


@login_required
def autocomplete_item(request):
    if 'term' in request.GET:
        term = (request.GET.get('term') or '').upper()
        with connection.cursor() as cursor:
            cursor.execute("SELECT item_name FROM Items WHERE UPPER(item_name) LIKE %s ORDER BY CASE WHEN UPPER(item_name) LIKE %s THEN 0 ELSE 1 END, item_name LIMIT 10", ['%' + term + '%', term + '%'])
            rows = cursor.fetchall()
        suggestions = [row[0] for row in rows]
        return JsonResponse(suggestions, safe=False)
    return JsonResponse([], safe=False)

@login_required
def items_hub(request):
    """
    Items landing page. Mirrors the Accounts Reports UI: a left panel with
    two options (Add Item / Update Item) and a right panel that shows the
    corresponding form. Add Item posts to create_new_item, Update Item uses
    update_item_view via AJAX.
    """
    if not request.user.has_perm("auth.view_item"):
        messages.error(request, "You do not have permission to view Items!")
        return redirect("home:home")
    return render(request, "items_templates/items.html")


@login_required
def items_list_json(request):
    """
    Returns the full catalogue of items as JSON for the 'All Items' table:
    name, price, storage, code, category, brand, who added/last-touched it,
    and the created/updated timestamps.
    """
    if not request.user.has_perm("auth.view_item"):
        return JsonResponse({"status": "error", "message": "You do not have permission to view Items!"}, status=403)

    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT i.item_id,
                   i.item_name,
                   i.sale_price,
                   i.storage,
                   i.item_code,
                   i.category,
                   i.brand,
                   COALESCE(u.username, 'N/A') AS created_by,
                   i.created_at,
                   i.updated_at
            FROM Items i
            LEFT JOIN auth_user u ON u.id = i.created_by
            ORDER BY i.created_at DESC NULLS LAST, i.item_id DESC
        """)
        rows = cursor.fetchall()

    def fmt(dt):
        return dt.strftime("%d %b %Y, %I:%M %p") if dt else ""

    items = [{
        "item_id": r[0],
        "item_name": r[1],
        "sale_price": str(r[2]) if r[2] is not None else "0.00",
        "storage": r[3] or "",
        "item_code": r[4] or "",
        "category": r[5] or "",
        "brand": r[6] or "",
        "created_by": r[7],
        "created_at": fmt(r[8]),
        "updated_at": fmt(r[9]),
    } for r in rows]

    return JsonResponse({"status": "success", "count": len(items), "items": items})
