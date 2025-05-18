from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('register/', views.register, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('portfolio/', views.portfolio_list, name='portfolio_list'),
    path('portfolio/add/', views.portfolio_add, name='portfolio_add'),
    path('portfolio/edit/<int:portfolio_id>/', views.portfolio_edit, name='portfolio_edit'),
    path('get-current-price/', views.get_current_price, name='get_current_price'),
    path('portfolio/add_quantity/', views.add_quantity, name='add_quantity'),
    path('portfolio/remove_quantity/', views.remove_quantity, name='remove_quantity'),
] 