from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('rooms/', views.rooms, name='rooms'),
    path('rooms/<str:slug>/', views.room_detail, name='room_detail'),
    path('facilities/', views.facilities, name='facilities'),
    path('booking/', views.booking, name='booking'),
    path('contact/', views.contact, name='contact'),
    path('privacy-policy/', views.privacy_policy, name='privacy_policy'),

]

