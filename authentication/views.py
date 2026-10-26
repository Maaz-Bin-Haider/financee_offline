from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from financee.security import rate_limit, safe_json_error, user_has_active_company

@rate_limit("login", limit=10, window=60, methods={"POST"})
def login_view(request):
    if request.user.is_authenticated:
        if not user_has_active_company(request.user) and request.user.is_staff:
            return redirect('/admin/')
        return redirect('home:home')
    if request.method == 'POST':
        try:
            username = request.POST.get('username')
            password = request.POST.get('password')

            if not username or not password:
                return JsonResponse({
                    'status': 'error',
                    'message': 'Please enter both username and password.'
                })

            user = authenticate(request, username=username, password=password)

            if user is not None:
                login(request, user)
                redirect_url = "/admin/" if (
                    not user_has_active_company(user) and user.is_staff
                ) else "/home/"
                return JsonResponse({
                    'status': 'success',
                    'message': f'Welcome back, {user.username}!',
                    'redirect_url': redirect_url,
                })
            else:
                return JsonResponse({
                    'status': 'error',
                    'message': 'Invalid username or password.'
                })
        except Exception:
            return safe_json_error("Login failed. Please try again.", status=500)

    return render(request, 'authentication_templates/login_template.html')


@login_required
def logout_view(request):
    try:
        logout(request)
        return redirect('authentication:login')
    except Exception:
        return safe_json_error("Logout failed. Please try again.", status=500)



@login_required
def current_user(request):
    data = {
        "username": request.user.username,
    }
    return JsonResponse(data)
