from django.contrib.auth.views import LogoutView
from django.urls import path

from . import views


app_name = 'library'

urlpatterns = [
    path('', views.home, name='home'),

    path('catalog/', views.catalog, name='catalog'),
    path('catalog/export/', views.export_books_csv, name='export_books_csv'),

    path('authors/', views.authors, name='authors'),
    path('authors/create/', views.create_author, name='create_author'),
    path('authors/<int:pk>/edit/', views.update_author, name='update_author'),

    path('categories/', views.categories_list, name='categories'),
    path('categories/create/', views.create_category, name='create_category'),
    path('categories/<int:pk>/edit/', views.update_category, name='update_category'),

    path('books/create/', views.create_book, name='create_book'),
    path('books/<int:pk>/', views.book_detail, name='book_detail'),
    path('books/<int:pk>/edit/', views.update_book, name='update_book'),
    path('books/<int:pk>/delete/', views.delete_book, name='delete_book'),

    path('readers/<int:pk>/', views.reader_detail, name='reader_detail'),
    path('readers/', views.readers, name='readers'),
    path('readers/<int:pk>/edit/', views.update_reader, name='update_reader'),

    path('loans/', views.loans, name='loans'),
    path('loans/export/', views.export_loans_csv, name='export_loans_csv'),
    path('loans/create/', views.create_loan, name='create_loan'),
    path('loans/<int:pk>/return/', views.return_loan, name='return_loan'),

    path('statistics/', views.statistics, name='statistics'),

    path('login/', views.LibraryLoginView.as_view(), name='login'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('register/', views.register, name='register'),
]