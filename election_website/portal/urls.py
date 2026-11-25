from django.urls import path

from . import views

urlpatterns = [
    path('', views.home, name='portal_home'),
    path('signin/', views.signin, name='portal_signin'),
    path('signout/', views.signout, name='portal_signout'),
    path('vote/', views.vote, name='portal_vote'),
    path('receipt/', views.receipt, name='portal_receipt'),
    path('results/', views.results, name='portal_results'),
    path('explorer/', views.explorer, name='portal_explorer'),
    path('control/', views.control, name='portal_control'),

    path('api/overview/', views.api_overview, name='portal_api_overview'),
    path('api/chain/', views.api_chain, name='portal_api_chain'),
    path('api/vote/', views.api_vote, name='portal_api_vote'),
    path('api/verify/', views.api_verify, name='portal_api_verify'),
    path('api/tamper/', views.api_tamper, name='portal_api_tamper'),
]
