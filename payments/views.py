from activity.recorder import record as record_activity
# from django.shortcuts import render,redirect

import logging
logger = logging.getLogger(__name__)
# from django.db import connection,DatabaseError
# from django.contrib import messages
# from datetime import datetime, date
# from django.http import JsonResponse
# import json
# from psycopg2.extras import Json
# from django.contrib.auth.decorators import login_required

# # Create your views here.

# @login_required
# def make_payment(request):
#     if not request.user.has_perm("auth.view_payment"):
#         messages.error(request, "You do not have permission to view payments.")
#         return redirect("home:home")
    
#     if request.method == 'POST':
#         action = request.POST.get("action")
#         payment_id = request.POST.get("current_id")
#         if action == "submit":
#             payment_date_str = request.POST.get('payment_date')
#             party_name = request.POST.get('search_name')
#             amount_str = request.POST.get('amount')
#             description = request.POST.get('description')

#             data = {
#                 "party_name":party_name.upper(),
#                 "amount": amount_str,
#                 "method": "Cash",
#                 "description": description if description else '',
#                 "payment_date": payment_date_str
#             }

#             # If party name is Empty
#             if not party_name:
#                 messages.error(request,"Please Enter a party Name!")
#                 return render(request,"payments_templates/payment.html",data)

#             # Validating Amount
#             try:
#                 amount = float(amount_str)
#                 if amount <= 0:
#                     messages.error(request,"Amount must be greater than Zero.")
#                     return render(request,"payments_templates/payment.html",data)
#             except:
#                 messages.error(request,"Invalid amount. Please enter a valid number.")
#                 return render(request,"payments_templates/payment.html",data)

#             # Validate payment_date (must be in correct date format)
#             try:
#                 # Adjust format according to your input (e.g. "YYYY-MM-DD")
#                 payment_date = datetime.strptime(payment_date_str, "%Y-%m-%d").date()

#                 # Future Date Restriction
#                 if payment_date > date.today():
#                     messages.error(request, "Payment date cannot be in the future.")
#                     return render(request,"payments_templates/payment.html",data)

#                 # Making Date again Str
#                 payment_date = payment_date.strftime("%Y-%m-%d")

#             except (ValueError, TypeError):
#                 messages.error(request,"Invalid date. Please enter a valid date in YYYY-MM-DD format.")
#                 return render(request,"payments_templates/payment.html",data)

            
#             # validating party_name and Inserting Data
#             with connection.cursor() as cursor:
#                 cursor.execute("SELECT 1 FROM Parties WHERE UPPER(party_name) = %s",[party_name.upper()])
#                 exists = cursor.fetchone()
#                 if exists:
#                     # data = {
#                     #         "party_name":party_name.upper(),
#                     #         "amount": amount,
#                     #         "method": "Cash",
#                     #         "description": description if description else '',
#                     #         "payment_date": payment_date
#                     #     }
#                     # json_data = json.dumps(data)
#                     data = {
#                         "party_name": party_name.upper(),
#                         "amount": amount,
#                         "method": "Cash",
#                         "description": description if description else '',
#                         "payment_date": payment_date,
#                         "created_by_id": request.user.id      # <-- added
#                     }
#                     json_data = json.dumps(data)
                    
#                     if not payment_id: # Means new payment
#                         try:
#                             # Condition Check for view_only_user group
#                             if request.user.groups.filter(name="view_only_users").exists():
#                                 messages.error(request,"You do not have permission to Make or Update payments.")
#                                 return redirect("payments:payment") 
                            
#                             # Access check for create payment right
#                             if not request.user.has_perm("auth.create_payment"):
#                                 messages.error(request, "You do not have permission to Create payments.")
#                                 return redirect("payments:payment")

#                             cursor.execute("SELECT make_payment(%s)",[json_data])
#                             messages.success(request, f"Transaction completed: {amount} paid to {party_name}.")
#                             return redirect("payments:payment")
#                         except Exception as e:
#                             messages.error(request,f"An Unexpected Error occured Please Try Again! {e}")
#                     else:   # Means we have to update payment 
#                         try:
#                             # Condition Check for view_only_user group
#                             if request.user.groups.filter(name="view_only_users").exists():
#                                 messages.error(request,"You do not have permission to Make or Update payments.")
#                                 return redirect("payments:payment") 
                            
#                             # Access check for update payment right
#                             if not request.user.has_perm("auth.update_payment"):
#                                 messages.error(request, "You do not have permission to Update payments.")
#                                 return redirect("payments:payment")

#                             cursor.execute("SELECT update_payment(%s,%s)",[payment_id,json_data])
#                             messages.success(request, f"Transaction Updated: {amount} paid to {party_name}.")
#                             return redirect("payments:payment")
#                         except Exception as e:
#                             messages.error(request,f"An Unexpected Error occured Please Try Again! {e}")
#                 else:
#                     messages.error(request,f"No such Party exists with name '{party_name}'!")
#                     return render(request,"payments_templates/payment.html",data)
#         if action == "delete":

            
#             if not payment_id:
#                 messages.error(request,"Navigate to Payment first which you want to delete")
#                 return render(request,"payments_templates/payment.html")
#             try:
#                 payment_id = int(payment_id)
#             except:
#                 messages.error(request,"Navigate to Payment first which you want to delete")
#                 return render(request,"payments_templates/payment.html")
            
#             try:
#                 # Condition Check for view_only_user group
#                 if request.user.groups.filter(name="view_only_users").exists():
#                     messages.error(request,"You do not have permission to Delete payments.")
#                     return redirect("payments:payment") 
                
#                 # Access check for delete payment right
#                 if not request.user.has_perm("auth.delete_payment"):
#                     messages.error(request, "You do not have permission to Delete payments.")
#                     return redirect("payments:payment")

#                 with connection.cursor() as cursor:
#                     cursor.execute("SELECT delete_payment(%s)",[payment_id])
#                     messages.success(request,"Payment delete Sucessfully.")
#                     return redirect("payments:payment")
#             except Exception:
#                 messages.error(request,"Unable to delete this Payment! Try Again..")
#                 return render(request,"payments_templates/payment.html")
            
#     return render(request,"payments_templates/payment.html")

# # if action is previous it call previous function from DB,
# #  if next then same and if no action is provided it call get_payment_details() which fetches current payment using ID.
# @login_required
# def get_payment(request):
#     action = request.GET.get("action")
#     current_id = request.GET.get("current_id")
#     try:
#         with connection.cursor() as cursor:
#             if action == "previous":
#                 if not current_id:
#                     cursor.execute("SELECT get_last_payment()")
#                     last_payment = cursor.fetchone()
#                     if not last_payment or not last_payment[0]:
#                         return JsonResponse({"error": "No payments found."}, status=404)
                    
#                     try:
#                         last_payment = json.loads(last_payment[0])
#                         current_id = int(last_payment['payment_id']) + 1
#                     except Exception:
#                         return JsonResponse({"error":"Invalid last payment data"},status=500)

#                 try:
#                         current_id = int(current_id)
#                 except (ValueError, TypeError):
#                     return JsonResponse({"error": "Invalid current_id."}, status=400)
                

#                 cursor.execute("SELECT get_previous_payment(%s)", [current_id])
#                 result = cursor.fetchone()

#                 if not result or not result[0]:
                    
#                     return JsonResponse({
#                         "error": "No previous payment found.",
#                         "info": "You are already at the first payment."
#                     }, status=404)
                
#             elif action == "next":
#                 try:
#                     current_id = int(current_id)
#                 except (ValueError, TypeError):
#                     return JsonResponse({"error": "Invalid current_id."}, status=400)

#                 cursor.execute("SELECT get_next_payment(%s)", [current_id])
#                 result = cursor.fetchone()

#                 if not result or not result[0]:
                    
#                     return JsonResponse({
#                         "error": "No next payment found.",
#                         "info": "You are already at the latest payment."
#                     }, status=404)
#             else: # No action is provided means we have to fetch payment with current ID
#                 try:
#                     current_id = int(current_id)
#                 except (ValueError, TypeError):
#                     return JsonResponse({"error": "Invalid current_id."}, status=400)

#                 cursor.execute("SELECT get_payment_details(%s)", [current_id])
#                 result = cursor.fetchone()

#                 if not result or not result[0]:
                    
#                     return JsonResponse({
#                         "error": "No payment found.",
#                         "info": "Can't Find this payment may be some Internet issue!."
#                     }, status=404)
#     except DatabaseError:
#          return JsonResponse({"error": "Database error."}, status=500)


#     try:
#         return JsonResponse(json.loads(result[0]))
#     except Exception:
#         return JsonResponse({"error": "Invalid payment data format."}, status=500)


# @login_required
# def get_old_payments(request):
#     try:
#         with connection.cursor() as cursor:
#             cursor.execute("SELECT get_last_20_payments_json(%s)", [Json({})])
#             data = cursor.fetchone()

#         if not data or not data[0]:
#             return JsonResponse(
#                 {"error": "No payment data found."}, 
#                 status=404
#             )

#         try:
#             data = json.loads(data[0])
#         except (json.JSONDecodeError, TypeError):
#             return JsonResponse(
#                 {"error": "Failed to parse payment data."}, 
#                 status=500
#             )

#         return JsonResponse(data, safe=False)

#     except DatabaseError as e:
#         return JsonResponse(
#             {"error": "Database error occurred.", "details": str(e)}, 
#             status=500
#         )
#     except Exception as e:
#         return JsonResponse(
#             {"error": "An unexpected error occurred.", "details": str(e)}, 
#             status=500
#         )
    
# @login_required
# def get_payments_date_wise(request):
#     try:
#         from_date_str = request.GET.get("from")
#         to_date_str = request.GET.get("to")

#         if not from_date_str or not to_date_str:
#             return JsonResponse({"error": "Missing date range"}, status=400)
        
#         # Validating Dates (must be in correct date format)
#         try:
#             # Adjust format according to your input (e.g. "YYYY-MM-DD")
#             from_date = datetime.strptime(from_date_str, "%Y-%m-%d").date()
#             to_date = datetime.strptime(to_date_str, "%Y-%m-%d").date()

#             # Future Date Restriction
#             if from_date > date.today() or to_date > date.today():
#                 return JsonResponse({"error": "Dates can't be in Future"}, status=400)

#             # Making Date again Str
#             from_date = from_date.strftime("%Y-%m-%d")
#             to_date = to_date.strftime("%Y-%m-%d")

#         except (ValueError, TypeError):
#             JsonResponse({"error": "Invalid date. Please enter a valid date in YYYY-MM-DD format."}, status=400)
        
#         dates = {
#             "start_date": from_date,
#             "end_date": to_date
#         }

#         with connection.cursor() as cursor:
#             cursor.execute(
#                 "SELECT get_payments_by_date_json(%s)",
#                 [json.dumps(dates)]
#             )
#             data = cursor.fetchone()

#         if not data or not data[0]:
#             return JsonResponse([], safe=False)
        
#         try:
#             data = json.loads(data[0])
#         except (json.JSONDecodeError, TypeError):
#             return JsonResponse(
#                 {"error": "Failed to parse payment data."}, 
#                 status=500
#             )

#         return JsonResponse(data, safe=False)

#     except Exception as e:
#         return JsonResponse({"error": str(e)}, status=500)
    

# from django.shortcuts import render,redirect
# from django.db import connection,DatabaseError
# from django.contrib import messages
# from datetime import datetime, date
# from django.http import JsonResponse
# import json
# from psycopg2.extras import Json
# from django.contrib.auth.decorators import login_required

# # Create your views here.

# @login_required
# def make_payment(request):
#     if not request.user.has_perm("auth.view_payment"):
#         messages.error(request, "You do not have permission to view payments.")
#         return redirect("home:home")
    
#     if request.method == 'POST':
#         action = request.POST.get("action")
#         payment_id = request.POST.get("current_id")
#         if action == "submit":
#             payment_date_str = request.POST.get('payment_date')
#             party_name = request.POST.get('search_name')
#             amount_str = request.POST.get('amount')
#             description = request.POST.get('description')

#             data = {
#                 "party_name":party_name.upper(),
#                 "amount": amount_str,
#                 "method": "Cash",
#                 "description": description if description else '',
#                 "payment_date": payment_date_str
#             }

#             # If party name is Empty
#             if not party_name:
#                 messages.error(request,"Please Enter a party Name!")
#                 return render(request,"payments_templates/payment.html",data)

#             # Validating Amount
#             try:
#                 amount = float(amount_str)
#                 if amount <= 0:
#                     messages.error(request,"Amount must be greater than Zero.")
#                     return render(request,"payments_templates/payment.html",data)
#             except:
#                 messages.error(request,"Invalid amount. Please enter a valid number.")
#                 return render(request,"payments_templates/payment.html",data)

#             # Validate payment_date (must be in correct date format)
#             try:
#                 # Adjust format according to your input (e.g. "YYYY-MM-DD")
#                 payment_date = datetime.strptime(payment_date_str, "%Y-%m-%d").date()

#                 # Future Date Restriction
#                 if payment_date > date.today():
#                     messages.error(request, "Payment date cannot be in the future.")
#                     return render(request,"payments_templates/payment.html",data)

#                 # Making Date again Str
#                 payment_date = payment_date.strftime("%Y-%m-%d")

#             except (ValueError, TypeError):
#                 messages.error(request,"Invalid date. Please enter a valid date in YYYY-MM-DD format.")
#                 return render(request,"payments_templates/payment.html",data)

            
#             # validating party_name and Inserting Data
#             with connection.cursor() as cursor:
#                 cursor.execute("SELECT 1 FROM Parties WHERE UPPER(party_name) = %s",[party_name.upper()])
#                 exists = cursor.fetchone()
#                 if exists:
#                     data = {
#                             "party_name":party_name.upper(),
#                             "amount": amount,
#                             "method": "Cash",
#                             "description": description if description else '',
#                             "payment_date": payment_date,
#                             "created_by_id": request.user.id
#                         }
#                     json_data = json.dumps(data)
                    
#                     if not payment_id: # Means new payment
#                         try:
#                             # Condition Check for view_only_user group
#                             if request.user.groups.filter(name="view_only_users").exists():
#                                 messages.error(request,"You do not have permission to Make or Update payments.")
#                                 return redirect("payments:payment") 
                            
#                             # Access check for create payment right
#                             if not request.user.has_perm("auth.create_payment"):
#                                 messages.error(request, "You do not have permission to Create payments.")
#                                 return redirect("payments:payment")

#                             cursor.execute("SELECT make_payment(%s)",[json_data])
#                             messages.success(request, f"Transaction completed: {amount} paid to {party_name}.")
#                             return redirect("payments:payment")
#                         except Exception as e:
#                             messages.error(request,f"An Unexpected Error occured Please Try Again! {e}")
#                     else:   # Means we have to update payment 
#                         try:
#                             # Condition Check for view_only_user group
#                             if request.user.groups.filter(name="view_only_users").exists():
#                                 messages.error(request,"You do not have permission to Make or Update payments.")
#                                 return redirect("payments:payment") 
                            
#                             # Access check for update payment right
#                             if not request.user.has_perm("auth.update_payment"):
#                                 messages.error(request, "You do not have permission to Update payments.")
#                                 return redirect("payments:payment")

#                             cursor.execute("SELECT update_payment(%s,%s)",[payment_id,json_data])
#                             messages.success(request, f"Transaction Updated: {amount} paid to {party_name}.")
#                             return redirect("payments:payment")
#                         except Exception as e:
#                             messages.error(request,f"An Unexpected Error occured Please Try Again! {e}")
#                 else:
#                     messages.error(request,f"No such Party exists with name '{party_name}'!")
#                     return render(request,"payments_templates/payment.html",data)
#         if action == "delete":

            
#             if not payment_id:
#                 messages.error(request,"Navigate to Payment first which you want to delete")
#                 return render(request,"payments_templates/payment.html")
#             try:
#                 payment_id = int(payment_id)
#             except:
#                 messages.error(request,"Navigate to Payment first which you want to delete")
#                 return render(request,"payments_templates/payment.html")
            
#             try:
#                 # Condition Check for view_only_user group
#                 if request.user.groups.filter(name="view_only_users").exists():
#                     messages.error(request,"You do not have permission to Delete payments.")
#                     return redirect("payments:payment") 
                
#                 # Access check for delete payment right
#                 if not request.user.has_perm("auth.delete_payment"):
#                     messages.error(request, "You do not have permission to Delete payments.")
#                     return redirect("payments:payment")

#                 with connection.cursor() as cursor:
#                     cursor.execute("SELECT delete_payment(%s)",[payment_id])
#                     messages.success(request,"Payment delete Sucessfully.")
#                     return redirect("payments:payment")
#             except Exception:
#                 messages.error(request,"Unable to delete this Payment! Try Again..")
#                 return render(request,"payments_templates/payment.html")
            
#     return render(request,"payments_templates/payment.html")

# # if action is previous it call previous function from DB,
# #  if next then same and if no action is provided it call get_payment_details() which fetches current payment using ID.
# @login_required
# def get_payment(request):
#     action = request.GET.get("action")
#     current_id = request.GET.get("current_id")
#     try:
#         with connection.cursor() as cursor:
#             if action == "previous":
#                 if not current_id:
#                     cursor.execute("SELECT get_last_payment()")
#                     last_payment = cursor.fetchone()
#                     if not last_payment or not last_payment[0]:
#                         return JsonResponse({"error": "No payments found."}, status=404)
                    
#                     try:
#                         last_payment = json.loads(last_payment[0])
#                         current_id = int(last_payment['payment_id']) + 1
#                     except Exception:
#                         return JsonResponse({"error":"Invalid last payment data"},status=500)

#                 try:
#                         current_id = int(current_id)
#                 except (ValueError, TypeError):
#                     return JsonResponse({"error": "Invalid current_id."}, status=400)
                

#                 cursor.execute("SELECT get_previous_payment(%s)", [current_id])
#                 result = cursor.fetchone()

#                 if not result or not result[0]:
                    
#                     return JsonResponse({
#                         "error": "No previous payment found.",
#                         "info": "You are already at the first payment."
#                     }, status=404)
                
#             elif action == "next":
#                 try:
#                     current_id = int(current_id)
#                 except (ValueError, TypeError):
#                     return JsonResponse({"error": "Invalid current_id."}, status=400)

#                 cursor.execute("SELECT get_next_payment(%s)", [current_id])
#                 result = cursor.fetchone()

#                 if not result or not result[0]:
                    
#                     return JsonResponse({
#                         "error": "No next payment found.",
#                         "info": "You are already at the latest payment."
#                     }, status=404)
#             else: # No action is provided means we have to fetch payment with current ID
#                 try:
#                     current_id = int(current_id)
#                 except (ValueError, TypeError):
#                     return JsonResponse({"error": "Invalid current_id."}, status=400)

#                 cursor.execute("SELECT get_payment_details(%s)", [current_id])
#                 result = cursor.fetchone()

#                 if not result or not result[0]:
                    
#                     return JsonResponse({
#                         "error": "No payment found.",
#                         "info": "Can't Find this payment may be some Internet issue!."
#                     }, status=404)
#     except DatabaseError:
#          return JsonResponse({"error": "Database error."}, status=500)


#     try:
#         return JsonResponse(json.loads(result[0]))
#     except Exception:
#         return JsonResponse({"error": "Invalid payment data format."}, status=500)


# @login_required
# def get_old_payments(request):
#     try:
#         with connection.cursor() as cursor:
#             cursor.execute("SELECT get_last_20_payments_json(%s)", [Json({})])
#             data = cursor.fetchone()

#         if not data or not data[0]:
#             return JsonResponse(
#                 {"error": "No payment data found."}, 
#                 status=404
#             )

#         try:
#             data = json.loads(data[0])
#         except (json.JSONDecodeError, TypeError):
#             return JsonResponse(
#                 {"error": "Failed to parse payment data."}, 
#                 status=500
#             )

#         return JsonResponse(data, safe=False)

#     except DatabaseError as e:
#         return JsonResponse(
#             {"error": "Database error occurred.", "details": str(e)}, 
#             status=500
#         )
#     except Exception as e:
#         return JsonResponse(
#             {"error": "An unexpected error occurred.", "details": str(e)}, 
#             status=500
#         )
    
# @login_required
# def get_payments_date_wise(request):
#     try:
#         from_date_str = request.GET.get("from")
#         to_date_str = request.GET.get("to")

#         if not from_date_str or not to_date_str:
#             return JsonResponse({"error": "Missing date range"}, status=400)
        
#         # Validating Dates (must be in correct date format)
#         try:
#             # Adjust format according to your input (e.g. "YYYY-MM-DD")
#             from_date = datetime.strptime(from_date_str, "%Y-%m-%d").date()
#             to_date = datetime.strptime(to_date_str, "%Y-%m-%d").date()

#             # Future Date Restriction
#             if from_date > date.today() or to_date > date.today():
#                 return JsonResponse({"error": "Dates can't be in Future"}, status=400)

#             # Making Date again Str
#             from_date = from_date.strftime("%Y-%m-%d")
#             to_date = to_date.strftime("%Y-%m-%d")

#         except (ValueError, TypeError):
#             JsonResponse({"error": "Invalid date. Please enter a valid date in YYYY-MM-DD format."}, status=400)
        
#         dates = {
#             "start_date": from_date,
#             "end_date": to_date
#         }

#         with connection.cursor() as cursor:
#             cursor.execute(
#                 "SELECT get_payments_by_date_json(%s)",
#                 [json.dumps(dates)]
#             )
#             data = cursor.fetchone()

#         if not data or not data[0]:
#             return JsonResponse([], safe=False)
        
#         try:
#             data = json.loads(data[0])
#         except (json.JSONDecodeError, TypeError):
#             return JsonResponse(
#                 {"error": "Failed to parse payment data."}, 
#                 status=500
#             )

#         return JsonResponse(data, safe=False)

#     except Exception as e:
#         return JsonResponse({"error": str(e)}, status=500)


from django.shortcuts import render,redirect
from django.db import connection,DatabaseError
from django.contrib import messages
from datetime import datetime, date
from django.http import JsonResponse
import json
from psycopg2.extras import Json
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from attachments.utils import delete_document_attachments, save_document_attachments, validate_request_attachments

# Create your views here.

@login_required
def make_payment(request):
    if not request.user.has_perm("auth.view_payment"):
        messages.error(request, "You do not have permission to view payments.")
        return redirect("home:home")
    
    if request.method == 'POST':
        action = request.POST.get("action")
        payment_id = request.POST.get("current_id")
        if action == "submit":
            payment_date_str = request.POST.get('payment_date')
            party_name = request.POST.get('search_name')
            amount_str = request.POST.get('amount')
            description = request.POST.get('description')

            data = {
                "party_name":party_name.upper(),
                "amount": amount_str,
                "method": "Cash",
                "description": description if description else '',
                "payment_date": payment_date_str
            }

            try:
                validate_request_attachments(request)
            except ValidationError as e:
                messages.error(request, e.messages[0] if hasattr(e, "messages") else str(e))
                return render(request,"payments_templates/payment.html",data)

            # If party name is Empty
            if not party_name:
                messages.error(request,"Please Enter a party Name!")
                return render(request,"payments_templates/payment.html",data)

            # Validating Amount
            try:
                amount = float(amount_str)
                if amount <= 0:
                    messages.error(request,"Amount must be greater than Zero.")
                    return render(request,"payments_templates/payment.html",data)
            except Exception as e:
                logger.exception('swallowed exception in %s', __name__)
                messages.error(request,"Invalid amount. Please enter a valid number.")
                return render(request,"payments_templates/payment.html",data)

            # Validate payment_date (must be in correct date format)
            try:
                # Adjust format according to your input (e.g. "YYYY-MM-DD")
                payment_date = datetime.strptime(payment_date_str, "%Y-%m-%d").date()

                # Future Date Restriction
                if payment_date > date.today():
                    messages.error(request, "Payment date cannot be in the future.")
                    return render(request,"payments_templates/payment.html",data)

                # Making Date again Str
                payment_date = payment_date.strftime("%Y-%m-%d")

            except (ValueError, TypeError):
                messages.error(request,"Invalid date. Please enter a valid date in YYYY-MM-DD format.")
                return render(request,"payments_templates/payment.html",data)

            
            # validating party_name and Inserting Data
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1 FROM Parties WHERE UPPER(party_name) = %s",[party_name.upper()])
                exists = cursor.fetchone()
                if exists:
                    data = {
                            "party_name":party_name.upper(),
                            "amount": amount,
                            "method": "Cash",
                            "description": description if description else '',
                            "payment_date": payment_date,
                            "created_by_id": request.user.id
                        }
                    json_data = json.dumps(data)
                    
                    if not payment_id: # Means new payment
                        try:
                            # Condition Check for view_only_user group
                            if request.user.groups.filter(name="view_only_users").exists():
                                messages.error(request,"You do not have permission to Make or Update payments.")
                                return redirect("payments:payment") 
                            
                            # Access check for create payment right
                            if not request.user.has_perm("auth.create_payment"):
                                messages.error(request, "You do not have permission to Create payments.")
                                return redirect("payments:payment")

                            cursor.execute("SELECT make_payment(%s)",[json_data])
                            result = cursor.fetchone()[0]
                            new_payment_id = result.get("payment_id") if isinstance(result, dict) else json.loads(result).get("payment_id")
                            save_document_attachments(request, "payment", new_payment_id)
                            messages.success(request, f"Transaction completed: {amount} paid to {party_name}.")
                            record_activity(request, 'create', 'payment', new_payment_id, f'Payment #{new_payment_id}')
                            return redirect("payments:payment")
                        except ValidationError as e:
                            messages.error(request, e.messages[0] if hasattr(e, "messages") else str(e))
                        except Exception as e:
                            messages.error(request,f"An Unexpected Error occured Please Try Again! {e}")
                    else:   # Means we have to update payment 
                        try:
                            # Condition Check for view_only_user group
                            if request.user.groups.filter(name="view_only_users").exists():
                                messages.error(request,"You do not have permission to Make or Update payments.")
                                return redirect("payments:payment") 
                            
                            # Access check for update payment right
                            if not request.user.has_perm("auth.update_payment"):
                                messages.error(request, "You do not have permission to Update payments.")
                                return redirect("payments:payment")

                            cursor.execute("SELECT update_payment(%s,%s)",[payment_id,json_data])
                            save_document_attachments(request, "payment", payment_id)
                            messages.success(request, f"Transaction Updated: {amount} paid to {party_name}.")
                            record_activity(request, 'update', 'payment', payment_id, f'Payment #{payment_id}')
                            return redirect("payments:payment")
                        except ValidationError as e:
                            messages.error(request, e.messages[0] if hasattr(e, "messages") else str(e))
                        except Exception as e:
                            messages.error(request,f"An Unexpected Error occured Please Try Again! {e}")
                else:
                    messages.error(request,f"No such Party exists with name '{party_name}'!")
                    return render(request,"payments_templates/payment.html",data)
        if action == "delete":

            
            if not payment_id:
                messages.error(request,"Navigate to Payment first which you want to delete")
                return render(request,"payments_templates/payment.html")
            try:
                payment_id = int(payment_id)
            except Exception as e:
                logger.exception('swallowed exception in %s', __name__)
                messages.error(request,"Navigate to Payment first which you want to delete")
                return render(request,"payments_templates/payment.html")
            
            try:
                # Condition Check for view_only_user group
                if request.user.groups.filter(name="view_only_users").exists():
                    messages.error(request,"You do not have permission to Delete payments.")
                    return redirect("payments:payment") 
                
                # Access check for delete payment right
                if not request.user.has_perm("auth.delete_payment"):
                    messages.error(request, "You do not have permission to Delete payments.")
                    return redirect("payments:payment")

                with connection.cursor() as cursor:
                    cursor.execute("SELECT delete_payment(%s)",[payment_id])
                    delete_document_attachments("payment", payment_id)
                    messages.success(request,"Payment delete Sucessfully.")
                    record_activity(request, 'delete', 'payment', payment_id, f'Payment #{payment_id}')
                    return redirect("payments:payment")
            except Exception:
                messages.error(request,"Unable to delete this Payment! Try Again..")
                return render(request,"payments_templates/payment.html")
            
    return render(request,"payments_templates/payment.html")

# if action is previous it call previous function from DB,
#  if next then same and if no action is provided it call get_payment_details() which fetches current payment using ID.
@login_required
def get_payment(request):
    action = request.GET.get("action")
    current_id = request.GET.get("current_id")
    try:
        with connection.cursor() as cursor:
            if action == "previous":
                if not current_id:
                    cursor.execute("SELECT get_last_payment()")
                    last_payment = cursor.fetchone()
                    if not last_payment or not last_payment[0]:
                        return JsonResponse({"error": "No payments found."}, status=404)
                    
                    try:
                        last_payment = json.loads(last_payment[0])
                        current_id = int(last_payment['payment_id']) + 1
                    except Exception:
                        return JsonResponse({"error":"Invalid last payment data"},status=500)

                try:
                        current_id = int(current_id)
                except (ValueError, TypeError):
                    return JsonResponse({"error": "Invalid current_id."}, status=400)
                

                cursor.execute("SELECT get_previous_payment(%s)", [current_id])
                result = cursor.fetchone()

                if not result or not result[0]:
                    
                    return JsonResponse({
                        "error": "No previous payment found.",
                        "info": "You are already at the first payment."
                    }, status=404)
                
            elif action == "next":
                try:
                    current_id = int(current_id)
                except (ValueError, TypeError):
                    return JsonResponse({"error": "Invalid current_id."}, status=400)

                cursor.execute("SELECT get_next_payment(%s)", [current_id])
                result = cursor.fetchone()

                if not result or not result[0]:
                    
                    return JsonResponse({
                        "error": "No next payment found.",
                        "info": "You are already at the latest payment."
                    }, status=404)
            else: # No action is provided means we have to fetch payment with current ID
                try:
                    current_id = int(current_id)
                except (ValueError, TypeError):
                    return JsonResponse({"error": "Invalid current_id."}, status=400)

                cursor.execute("SELECT get_payment_details(%s)", [current_id])
                result = cursor.fetchone()

                if not result or not result[0]:
                    
                    return JsonResponse({
                        "error": "No payment found.",
                        "info": "Can't Find this payment may be some Internet issue!."
                    }, status=404)
    except DatabaseError:
         return JsonResponse({"error": "Database error."}, status=500)


    try:
        return JsonResponse(json.loads(result[0]))
    except Exception:
        return JsonResponse({"error": "Invalid payment data format."}, status=500)


@login_required
def get_old_payments(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT get_last_20_payments_json(%s)", [Json({})])
            data = cursor.fetchone()

        if not data or not data[0]:
            return JsonResponse(
                {"error": "No payment data found."}, 
                status=404
            )

        try:
            data = json.loads(data[0])
        except (json.JSONDecodeError, TypeError):
            return JsonResponse(
                {"error": "Failed to parse payment data."}, 
                status=500
            )

        return JsonResponse(data, safe=False)

    except DatabaseError as e:
        return JsonResponse(
            {"error": "Database error occurred.", "details": str(e)}, 
            status=500
        )
    except Exception as e:
        return JsonResponse(
            {"error": "An unexpected error occurred.", "details": str(e)}, 
            status=500
        )
    
@login_required
def get_payments_date_wise(request):
    try:
        from_date_str = request.GET.get("from")
        to_date_str = request.GET.get("to")

        if not from_date_str or not to_date_str:
            return JsonResponse({"error": "Missing date range"}, status=400)
        
        # Validating Dates (must be in correct date format)
        try:
            # Adjust format according to your input (e.g. "YYYY-MM-DD")
            from_date = datetime.strptime(from_date_str, "%Y-%m-%d").date()
            to_date = datetime.strptime(to_date_str, "%Y-%m-%d").date()

            # Future Date Restriction
            if from_date > date.today() or to_date > date.today():
                return JsonResponse({"error": "Dates can't be in Future"}, status=400)

            # Making Date again Str
            from_date = from_date.strftime("%Y-%m-%d")
            to_date = to_date.strftime("%Y-%m-%d")

        except (ValueError, TypeError):
            JsonResponse({"error": "Invalid date. Please enter a valid date in YYYY-MM-DD format."}, status=400)
        
        dates = {
            "start_date": from_date,
            "end_date": to_date
        }

        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT get_payments_by_date_json(%s)",
                [json.dumps(dates)]
            )
            data = cursor.fetchone()

        if not data or not data[0]:
            return JsonResponse([], safe=False)
        
        try:
            data = json.loads(data[0])
        except (json.JSONDecodeError, TypeError):
            return JsonResponse(
                {"error": "Failed to parse payment data."}, 
                status=500
            )

        return JsonResponse(data, safe=False)

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
    

@login_required
def get_party_balance(request):
    """
    AJAX endpoint: returns the current balance for a party by name.
    Used by the payments page to display live balance when a party is selected.
 
    GET /payments/party-balance/?name=PARTY_NAME
    Response: { "found": true, "party_name": "...", "balance": 12345.67, "party_type": "Customer" }
              { "found": false, "party_name": "..." }
              { "error": "..." }   on bad input or DB error
    """
    party_name = request.GET.get("name", "").strip()
 
    if not party_name:
        return JsonResponse({"error": "Party name is required."}, status=400)
 
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT get_party_balance_by_name(%s)",
                [party_name]
            )
            row = cursor.fetchone()
 
        if not row or row[0] is None:
            return JsonResponse({"found": False, "party_name": party_name})
 
        data = json.loads(row[0]) if isinstance(row[0], str) else row[0]
        return JsonResponse(data)
 
    except DatabaseError as e:
        return JsonResponse({"error": "Database error.", "details": str(e)}, status=500)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
