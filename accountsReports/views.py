from django.shortcuts import render,redirect
from django.db import connection, IntegrityError
from django.http import JsonResponse
import json
from datetime import datetime
from django.contrib.auth.decorators import login_required
from django.contrib import messages

@login_required
def detailed_ledger_view(request):
    if not request.user.has_perm("auth.view_accounts_reports_page") or not request.user.has_perm("auth.view_detailed_ledger"):
        messages.error(request, "Access Denied!")
        return redirect("home:home")
    
    if request.method == "GET":
        return render(request, "display_report_templates/accounts_reports_template.html")

    elif request.method == "POST":
        try:
            data = json.loads(request.body)
            party_name = data.get("party_name", "").strip()
            from_date = data.get("from_date")
            to_date = data.get("to_date")

            if not party_name or not from_date or not to_date:
                return JsonResponse({"error": "Missing required parameters."}, status=400)

            try:
                datetime.strptime(from_date, "%Y-%m-%d")
                datetime.strptime(to_date, "%Y-%m-%d")
            except ValueError:
                return JsonResponse({"error": "Invalid date format. Use YYYY-MM-DD."}, status=400)

            with connection.cursor() as cursor:
                cursor.execute("SELECT * FROM detailed_ledger(%s, %s, %s)", [party_name, from_date, to_date])
                columns = [col[0] for col in cursor.description]
                rows = cursor.fetchall()

            result = [dict(zip(columns, row)) for row in rows]
            return JsonResponse(result, safe=False)

        except IntegrityError as e:
            return JsonResponse({"error": f"Database error: {str(e)}"}, status=500)
        except Exception as e:
            return JsonResponse({"error": f"Unexpected error: {str(e)}"}, status=500)

    return JsonResponse({"error": "Method not allowed"}, status=405)


@login_required
def detailed_ledger2_view(request):
    if not request.user.has_perm("auth.view_accounts_reports_page") or not request.user.has_perm("auth.view_detailed_ledger"):
        messages.error(request, "Access Denied!")
        return redirect("home:home")

    if request.method == "GET":
        return render(request, "display_report_templates/accounts_reports_template.html")

    elif request.method == "POST":
        try:
            data = json.loads(request.body)
            party_name = data.get("party_name", "").strip()
            from_date  = data.get("from_date")
            to_date    = data.get("to_date")

            if not party_name or not from_date or not to_date:
                return JsonResponse({"error": "Missing required parameters."}, status=400)

            try:
                datetime.strptime(from_date, "%Y-%m-%d")
                datetime.strptime(to_date,   "%Y-%m-%d")
            except ValueError:
                return JsonResponse({"error": "Invalid date format. Use YYYY-MM-DD."}, status=400)

            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT * FROM detailed_ledger2(%s, %s, %s)",
                    [party_name, from_date, to_date]
                )
                columns = [col[0] for col in cursor.description]
                rows    = cursor.fetchall()

            result = []
            for row in rows:
                record = {}
                for col, val in zip(columns, row):
                    # invoice_details comes back as a dict (psycopg2 auto-parses jsonb)
                    if col == "invoice_details" and val is not None:
                        record[col] = val  # already a Python dict
                    elif hasattr(val, "isoformat"):
                        record[col] = val.isoformat()
                    else:
                        record[col] = val
                result.append(record)

            return JsonResponse(result, safe=False)

        except IntegrityError as e:
            return JsonResponse({"error": f"Database error: {str(e)}"}, status=500)
        except Exception as e:
            return JsonResponse({"error": f"Unexpected error: {str(e)}"}, status=500)

    return JsonResponse({"error": "Method not allowed"}, status=405)

@login_required
def cash_ledger_view(request):
    if not request.user.has_perm("auth.view_accounts_reports_page") or not request.user.has_perm("auth.view_cash_ledger"):
        messages.error(request, "Access Denied!")
        return redirect("home:home")
    
    if request.method == "GET":
        return render(request, "display_report_templates/accounts_reports_template.html")

    elif request.method == "POST":
        try:
            data = json.loads(request.body)
            from_date = data.get("from_date")
            to_date = data.get("to_date")

            if not from_date or not to_date:
                return JsonResponse({"error": "Missing required date parameters."}, status=400)

            try:
                datetime.strptime(from_date, "%Y-%m-%d")
                datetime.strptime(to_date, "%Y-%m-%d")
            except ValueError:
                return JsonResponse({"error": "Invalid date format. Use YYYY-MM-DD."}, status=400)

            with connection.cursor() as cursor:
                cursor.execute("SELECT * FROM get_cash_ledger_with_party(%s, %s)", [from_date, to_date])
                columns = [col[0] for col in cursor.description]
                rows = cursor.fetchall()

            result = [dict(zip(columns, row)) for row in rows]
            return JsonResponse(result, safe=False)

        except IntegrityError as e:
            return JsonResponse({"error": f"Database error: {str(e)}"}, status=500)
        except Exception as e:
            return JsonResponse({"error": f"Unexpected error: {str(e)}"}, status=500)

    return JsonResponse({"error": "Method not allowed"}, status=405)



@login_required
def trial_balance_view(request):
    if not request.user.has_perm("auth.view_accounts_reports_page")  or not request.user.has_perm("auth.view_trial_balance"):
        messages.error(request, "Access Denied!")
        return redirect("home:home")
    
    if request.method == "GET":
        return render(request, "display_report_templates/accounts_reports_template.html")

    elif request.method == "POST":
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT * FROM vw_trial_balance")
                columns = [col[0] for col in cursor.description]
                rows = cursor.fetchall()

            result = [dict(zip(columns, row)) for row in rows]
            return JsonResponse(result, safe=False)

        except IntegrityError as e:
            return JsonResponse({"error": f"Database error: {str(e)}"}, status=500)
        except Exception as e:
            return JsonResponse({"error": f"Unexpected error: {str(e)}"}, status=500)

    return JsonResponse({"error": "Method not allowed"}, status=405)

@login_required
def receivable(request):
    if not request.user.has_perm("auth.view_accounts_reports_page")  or not request.user.has_perm("auth.view_receivable"):
        messages.error(request, "Access Denied!")
        return redirect("home:home")
    
    if request.method == "GET":
        return render(request, "display_report_templates/accounts_reports_template.html")

    # elif request.method == "POST":
    #     try:
    #         with connection.cursor() as cursor:
    #             cursor.execute("SELECT get_accounts_receivable_json_excluding()")
    #             columns = [col[0] for col in cursor.description]
    #             rows = cursor.fetchall()

    #         result = [dict(zip(columns, row)) for row in rows]
    #         return JsonResponse(result, safe=False)

    #     except IntegrityError as e:
    #         return JsonResponse({"error": f"Database error: {str(e)}"}, status=500)
    #     except Exception as e:
    #         return JsonResponse({"error": f"Unexpected error: {str(e)}"}, status=500)
    elif request.method == "POST":
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT get_accounts_receivable_json_excluding()")
                data = cursor.fetchone()[0]   # get JSON directly
            print(type(data))
            return JsonResponse(data, safe=False)

        except IntegrityError as e:
            return JsonResponse({"error": f"Database error: {str(e)}"}, status=500)
        except Exception as e:
            
            return JsonResponse({"error": f"Unexpected error: {str(e)}"}, status=500)

    return JsonResponse({"error": "Method not allowed"}, status=405)

@login_required
def payable(request):
    if not request.user.has_perm("auth.view_accounts_reports_page")  or not request.user.has_perm("auth.view_payable"):
        messages.error(request, "Access Denied!")
        return redirect("home:home")
    
    if request.method == "GET":
        return render(request, "display_report_templates/accounts_reports_template.html")

    # elif request.method == "POST":
    #     try:
    #         with connection.cursor() as cursor:
    #             cursor.execute("SELECT get_accounts_payable_json_excluding()")
    #             columns = [col[0] for col in cursor.description]
    #             rows = cursor.fetchall()

    #         result = [dict(zip(columns, row)) for row in rows]
    #         return JsonResponse(result, safe=False)

    #     except IntegrityError as e:
    #         return JsonResponse({"error": f"Database error: {str(e)}"}, status=500)
    #     except Exception as e:
    #         return JsonResponse({"error": f"Unexpected error: {str(e)}"}, status=500)
    elif request.method == "POST":
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT get_accounts_payable_json_excluding()")
                data = cursor.fetchone()[0]   # get JSON directly

            return JsonResponse(data, safe=False)

        except IntegrityError as e:
            return JsonResponse({"error": f"Database error: {str(e)}"}, status=500)
        except Exception as e:
            
            return JsonResponse({"error": f"Unexpected error: {str(e)}"}, status=500)

    return JsonResponse({"error": "Method not allowed"}, status=405)



# Stock Report Serial Wise
@login_required
def stock_report_view(request):
    if not request.user.has_perm("auth.view_stock_reports_page") or not request.user.has_perm("auth.view_serial_wise_stock"):
        messages.error(request, "Access Denied!")
        return redirect("home:home")
    
    if request.method == "GET":
        return render(request, "display_report_templates/stock_reports_template.html")

    elif request.method == "POST":
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT * FROM stock_report")
                columns = [col[0] for col in cursor.description]
                rows = cursor.fetchall()

            result = [dict(zip(columns, row)) for row in rows]
            return JsonResponse(result, safe=False)

        except IntegrityError as e:
            return JsonResponse({"error": f"Database error: {str(e)}"}, status=500)
        except Exception as e:
            return JsonResponse({"error": f"Unexpected error: {str(e)}"}, status=500)

    return JsonResponse({"error": "Method not allowed"}, status=405)

# Stock Report Summary Wise
@login_required
def stock_summary(request):
    if not request.user.has_perm("auth.view_stock_reports_page") or not request.user.has_perm("auth.view_stock_summary"):
        messages.error(request, "Access Denied!")
        return redirect("home:home")
    
    if request.method == "GET":
        return render(request, "display_report_templates/stock_reports_template.html")
    

    elif request.method == "POST":
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT * FROM stock_summary();")
                columns = [col[0] for col in cursor.description]
                rows = cursor.fetchall()
                

            result = [dict(zip(columns, row)) for row in rows]
            return JsonResponse(result, safe=False)

        except IntegrityError as e:
            return JsonResponse({"error": f"Database error: {str(e)}"}, status=500)
        except Exception as e:
            return JsonResponse({"error": f"Unexpected error: {str(e)}"}, status=500)

    return JsonResponse({"error": "Method not allowed"}, status=405)



@login_required
def stock__worth_report_view(request):
    if not request.user.has_perm("auth.view_stock_reports_page") or not request.user.has_perm("auth.view_stock_worth_report"):
        messages.error(request, "Access Denied!")
        return redirect("home:home")
    
    if request.method == "GET":
        return render(request, "display_report_templates/stock_reports_template.html")

    elif request.method == "POST":
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT * FROM stock_worth_report")
                columns = [col[0] for col in cursor.description]
                rows = cursor.fetchall()

            result = [dict(zip(columns, row)) for row in rows]
            return JsonResponse(result, safe=False)

        except IntegrityError as e:
            return JsonResponse({"error": f"Database error: {str(e)}"}, status=500)
        except Exception as e:
            return JsonResponse({"error": f"Unexpected error: {str(e)}"}, status=500)

    return JsonResponse({"error": "Method not allowed"}, status=405)

@login_required
def item_history_view(request):
    if not request.user.has_perm("auth.view_stock_reports_page") or not request.user.has_perm("auth.view_item_history"):
        messages.error(request, "Access Denied!")
        return redirect("home:home")
    
    if request.method == "GET":
        return render(request, "display_report_templates/stock_reports_template.html")

    elif request.method == "POST":
        try:
            data = json.loads(request.body)
            item_name = data.get("item_name", "").strip()
            item_name_cap = item_name.upper()

            from_date = data.get("from_date")
            to_date = data.get("to_date")

            try:
                datetime.strptime(from_date, "%Y-%m-%d")
                datetime.strptime(to_date, "%Y-%m-%d")
            except ValueError:
                return JsonResponse({"error": "Invalid date format. Use YYYY-MM-DD."}, status=400)



            with connection.cursor() as cursor:
                cursor.execute("SELECT * FROM item_transaction_history(%s,%s, %s)",[item_name_cap,from_date,to_date])
                columns = [col[0] for col in cursor.description]
                rows = cursor.fetchall()

            result = [dict(zip(columns, row)) for row in rows]
            return JsonResponse(result, safe=False)

        except IntegrityError as e:
            return JsonResponse({"error": f"Database error: {str(e)}"}, status=500)
        except Exception as e:
            return JsonResponse({"error": f"Unexpected error: {str(e)}"}, status=500)

    return JsonResponse({"error": "Method not allowed"}, status=405)

@login_required
def item_detail_view(request):
    if not request.user.has_perm("auth.view_stock_reports_page") or not request.user.has_perm("auth.view_item_detail"):
        messages.error(request, "Access Denied!")
        return redirect("home:home")
    
    if request.method == "GET":
        return render(request, "display_report_templates/stock_reports_template.html")

    elif request.method == "POST":
        try:
            data = json.loads(request.body)
            item_name = data.get("item_name", "").strip()
            
            if not item_name:
                return JsonResponse({"error": "Item name is required"}, status=400)
            
            item_name_cap = item_name.upper()

            with connection.cursor() as cursor:
                cursor.execute("SELECT * FROM get_item_stock_by_name(%s)", [item_name_cap])
                columns = [col[0] for col in cursor.description]
                rows = cursor.fetchall()

            result = [dict(zip(columns, row)) for row in rows]
            return JsonResponse(result, safe=False)

        except IntegrityError as e:
            return JsonResponse({"error": f"Database error: {str(e)}"}, status=500)
        except Exception as e:
            return JsonResponse({"error": f"Unexpected error: {str(e)}"}, status=500)

    return JsonResponse({"error": "Method not allowed"}, status=405)

@login_required
def serial_ledger_view(request):
    if not request.user.has_perm("auth.view_stock_reports_page") or not request.user.has_perm("auth.view_serial_ledger"):
        messages.error(request, "Access Denied!")
        return redirect("home:home")
    
    if request.method == "GET":
        return render(request, "display_report_templates/stock_reports_template.html")

    elif request.method == "POST":
        try:
            data = json.loads(request.body)
            serial = data.get("serial", "").strip()

            if not serial:
                return JsonResponse({"error": "Serial is required"}, status=400)
            


            with connection.cursor() as cursor:
                cursor.execute("SELECT * FROM get_serial_ledger(%s)", [serial])
                columns = [col[0] for col in cursor.description]
                rows = cursor.fetchall()



            result = [dict(zip(columns, row)) for row in rows]


            return JsonResponse(result, safe=False)

        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)

    return JsonResponse({"error": "Method not allowed"}, status=405)

@login_required
def serial_ledger_purchase_only_view(request):
    if not request.user.has_perm("auth.view_stock_reports_page") or not request.user.has_perm("auth.view_serial_ledger_purchase_only"):
        messages.error(request, "Access Denied!")
        return redirect("home:home")
    
    if request.method == "GET":
        return render(request, "display_report_templates/stock_reports_template.html")

    elif request.method == "POST":
        try:
            data = json.loads(request.body)
            serial = data.get("serial", "").strip()

            if not serial:
                return JsonResponse({"error": "Serial is required"}, status=400)
            


            with connection.cursor() as cursor:
                cursor.execute("SELECT * FROM get_serial_ledger_purchase(%s)", [serial])
                columns = [col[0] for col in cursor.description]
                rows = cursor.fetchall()



            result = [dict(zip(columns, row)) for row in rows]


            return JsonResponse(result, safe=False)

        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)

    return JsonResponse({"error": "Method not allowed"}, status=405)


@login_required
def serial_ledger_view_sale_price_hidden(request):
    if not request.user.has_perm("auth.view_stock_reports_page") or not request.user.has_perm("auth.view_last_purchasing"):
        messages.error(request, "Access Denied!")
        return redirect("home:home")
    
    if request.method == "GET":
        return render(request, "display_report_templates/stock_reports_template.html")

    elif request.method == "POST":
        try:
            data = json.loads(request.body)
            serial = data.get("serial", "").strip()

            if not serial:
                return JsonResponse({"error": "Serial is required"}, status=400)
            


            with connection.cursor() as cursor:
                cursor.execute("SELECT serial_number, serial_comment, item_name, txn_date, particulars, reference, qty_in, qty_out, balance, party_name, purchase_price FROM get_serial_ledger(%s);", [serial])
                columns = [col[0] for col in cursor.description]
                rows = cursor.fetchall()



            result = [dict(zip(columns, row)) for row in rows]


            return JsonResponse(result, safe=False)

        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)

    return JsonResponse({"error": "Method not allowed"}, status=405)

@login_required
def serial_ledger_sale_only_view(request):
    if not request.user.has_perm("auth.view_stock_reports_page") or not request.user.has_perm("auth.view_serial_ledger_sale_only"):
        messages.error(request, "Access Denied!")
        return redirect("home:home")
    
    if request.method == "GET":
        return render(request, "display_report_templates/stock_reports_template.html")

    elif request.method == "POST":
        try:
            data = json.loads(request.body)
            serial = data.get("serial", "").strip()

            if not serial:
                return JsonResponse({"error": "Serial is required"}, status=400)
            


            with connection.cursor() as cursor:
                cursor.execute("SELECT * FROM get_serial_ledger_sales(%s)", [serial])
                columns = [col[0] for col in cursor.description]
                rows = cursor.fetchall()



            result = [dict(zip(columns, row)) for row in rows]


            return JsonResponse(result, safe=False)

        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)

    return JsonResponse({"error": "Method not allowed"}, status=405)


@login_required
def items_last_purchasing(request):
    if not request.user.has_perm("auth.view_stock_reports_page") or not request.user.has_perm("auth.view_last_purchasing"):
        messages.error(request, "Access Denied!")
        return redirect("home:home")
    
    if request.method == "GET":
        return render(request, "display_report_templates/stock_reports_template.html")

    elif request.method == "POST":
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT * FROM item_last_purchase_view")
                columns = [col[0] for col in cursor.description]
                rows = cursor.fetchall()

            result = [dict(zip(columns, row)) for row in rows]
            return JsonResponse(result, safe=False)

        except IntegrityError as e:
            return JsonResponse({"error": f"Database error: {str(e)}"}, status=500)
        except Exception as e:
            return JsonResponse({"error": f"Unexpected error: {str(e)}"}, status=500)

    return JsonResponse({"error": "Method not allowed"}, status=405)


@login_required
def items_last_sale(request):
    if not request.user.has_perm("auth.view_stock_reports_page") or not request.user.has_perm("auth.view_last_sale"):
        messages.error(request, "Access Denied!")
        return redirect("home:home")
    
    if request.method == "GET":
        return render(request, "display_report_templates/stock_reports_template.html")

    elif request.method == "POST":
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT * FROM item_last_sale_view")
                columns = [col[0] for col in cursor.description]
                rows = cursor.fetchall()

            result = [dict(zip(columns, row)) for row in rows]
            return JsonResponse(result, safe=False)

        except IntegrityError as e:
            return JsonResponse({"error": f"Database error: {str(e)}"}, status=500)
        except Exception as e:
            return JsonResponse({"error": f"Unexpected error: {str(e)}"}, status=500)

    return JsonResponse({"error": "Method not allowed"}, status=405)


# # =============================================================================
# # VIEW 1 – Monthly Company Position
# # =============================================================================
 
# @login_required
# def monthly_position_report(request):
#     """
#     GET  → renders the monthly reports HTML page (left panel will activate this)
#     POST → calls monthly_company_position(p_as_of_date) and returns JSON
#     """
#     if not request.user.has_perm("auth.view_sale_wise_profit_report"):
#         messages.error(request, "Access Denied!")
#         return redirect("home:home")
 
#     if request.method == "GET":
#         return render(request, "display_report_templates/monthly_reports_template.html")
 
#     elif request.method == "POST":
#         try:
#             data = json.loads(request.body)
#             as_of_date = data.get("as_of_date")
 
#             try:
#                 datetime.strptime(as_of_date, "%Y-%m-%d")
#             except (ValueError, TypeError):
#                 return JsonResponse({"error": "Invalid date format. Use YYYY-MM-DD."}, status=400)
 
#             with connection.cursor() as cursor:
#                 cursor.execute("SELECT monthly_company_position(%s)", [as_of_date])
#                 row = cursor.fetchone()
 
#             result = row[0] if row else None
#             if not result:
#                 return JsonResponse({"error": "No data found."}, status=404)
 
#             return JsonResponse(result, safe=False)
 
#         except IntegrityError as e:
#             return JsonResponse({"error": f"Database error: {str(e)}"}, status=500)
#         except Exception as e:
#             return JsonResponse({"error": f"Unexpected error: {str(e)}"}, status=500)
 
#     return JsonResponse({"error": "Method not allowed"}, status=405)
 
 
# # =============================================================================
# # VIEW 2 – Monthly Income Statement
# # =============================================================================
 
# @login_required
# def monthly_income_report(request):
#     """
#     GET  → renders the monthly reports HTML page
#     POST → calls monthly_income_statement(from, to) and returns JSON
#     """
#     if not request.user.has_perm("auth.view_sale_wise_profit_report"):
#         messages.error(request, "Access Denied!")
#         return redirect("home:home")
 
#     if request.method == "GET":
#         return render(request, "display_report_templates/monthly_reports_template.html")
 
#     elif request.method == "POST":
#         try:
#             data = json.loads(request.body)
#             from_date = data.get("from_date")
#             to_date = data.get("to_date")
 
#             try:
#                 datetime.strptime(from_date, "%Y-%m-%d")
#                 datetime.strptime(to_date, "%Y-%m-%d")
#             except (ValueError, TypeError):
#                 return JsonResponse({"error": "Invalid date format. Use YYYY-MM-DD."}, status=400)
 
#             with connection.cursor() as cursor:
#                 cursor.execute("SELECT monthly_income_statement(%s, %s)", [from_date, to_date])
#                 row = cursor.fetchone()
 
#             result = row[0] if row else None
#             if not result:
#                 return JsonResponse({"error": "No data found."}, status=404)
 
#             return JsonResponse(result, safe=False)
 
#         except IntegrityError as e:
#             return JsonResponse({"error": f"Database error: {str(e)}"}, status=500)
#         except Exception as e:
#             return JsonResponse({"error": f"Unexpected error: {str(e)}"}, status=500)
 
#     return JsonResponse({"error": "Method not allowed"}, status=405)


"""
Views for the two new monthly reports.
Add these functions to accountsReports/views.py
(also add them to the imports in urls.py)

New URL names (unique, won't conflict):
  monthly_position_report   -> /accountsReports/monthly-position/
  monthly_income_report     -> /accountsReports/monthly-income/
"""




# =============================================================================
# VIEW 1 – Monthly Company Position
# =============================================================================

@login_required
def monthly_position_report(request):
    """
    GET  → renders the monthly reports HTML page (left panel will activate this)
    POST → calls monthly_company_position(p_as_of_date) and returns JSON
    """
    if not request.user.has_perm("auth.view_sale_wise_profit_report"):
        messages.error(request, "Access Denied!")
        return redirect("home:home")

    if request.method == "GET":
        return render(request, "display_report_templates/monthly_reports_template.html")

    elif request.method == "POST":
        try:
            data = json.loads(request.body)
            as_of_date = data.get("as_of_date")

            try:
                datetime.strptime(as_of_date, "%Y-%m-%d")
            except (ValueError, TypeError):
                return JsonResponse({"error": "Invalid date format. Use YYYY-MM-DD."}, status=400)

            with connection.cursor() as cursor:
                cursor.execute("SELECT monthly_company_position(%s)", [as_of_date])
                row = cursor.fetchone()

            result = row[0] if row else None
            if not result:
                return JsonResponse({"error": "No data found."}, status=404)

            return JsonResponse(result, safe=False)

        except IntegrityError as e:
            return JsonResponse({"error": f"Database error: {str(e)}"}, status=500)
        except Exception as e:
            return JsonResponse({"error": f"Unexpected error: {str(e)}"}, status=500)

    return JsonResponse({"error": "Method not allowed"}, status=405)


# =============================================================================
# VIEW 2 – Monthly Income Statement
# =============================================================================

@login_required
def monthly_income_report(request):
    """
    GET  → renders the monthly reports HTML page
    POST → calls monthly_income_statement(from_date, to_date) and returns JSON.
           Sales, Purchases and Expenses are auto-calculated for the period
           (Pakistan model: Profit/Loss = Sales − Purchases − Expenses).
    """
    if not request.user.has_perm("auth.view_sale_wise_profit_report"):
        messages.error(request, "Access Denied!")
        return redirect("home:home")

    if request.method == "GET":
        return render(request, "display_report_templates/monthly_reports_template.html")

    elif request.method == "POST":
        try:
            data = json.loads(request.body)
            from_date = data.get("from_date")
            to_date   = data.get("to_date")

            try:
                datetime.strptime(from_date, "%Y-%m-%d")
                datetime.strptime(to_date, "%Y-%m-%d")
            except (ValueError, TypeError):
                return JsonResponse({"error": "Invalid date format. Use YYYY-MM-DD."}, status=400)

            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT monthly_income_statement(%s, %s)",
                    [from_date, to_date]
                )
                row = cursor.fetchone()

            result = row[0] if row else None
            if not result:
                return JsonResponse({"error": "No data found."}, status=404)

            return JsonResponse(result, safe=False)

        except IntegrityError as e:
            return JsonResponse({"error": f"Database error: {str(e)}"}, status=500)
        except Exception as e:
            return JsonResponse({"error": f"Unexpected error: {str(e)}"}, status=500)

    return JsonResponse({"error": "Method not allowed"}, status=405)



# @login_required
# def items_last_purchasing(request):
#     if not request.user.has_perm("auth.view_accounts_reports_page"):
#         messages.error(request, "Access Denied!")
#         return redirect("home:home")
    
#     if request.method == "GET":
#         return render(request, "display_report_templates/stock_reports_template.html")

#     elif request.method == "POST":
#         try:
#             with connection.cursor() as cursor:
#                 cursor.execute("SELECT * FROM item_last_purchase_view")  # or your view call
#                 row = cursor.fetchone()
#                 print(row)
#             # The function/view returns JSON — parse it if needed
#             result_json = row[0] if row else None
#             print(result_json,'----')
#             if not result_json:
#                 return JsonResponse({"error": "No data found."}, status=404)
#             print(result_json,'----')
#             return JsonResponse(result_json, safe=False)

#         except IntegrityError as e:
#             return JsonResponse({"error": f"Database error: {str(e)}"}, status=500)
#         except Exception as e:
#             return JsonResponse({"error": f"Unexpected error: {str(e)}"}, status=500)

#     return JsonResponse({"error": "Method not allowed"}, status=405)
