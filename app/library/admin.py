from django.contrib import admin

from .models import (
    Author,
    Book,
    BookAuthor,
    BookCategory,
    Category,
    Loan,
    Reader,
)


class BookAuthorInline(admin.TabularInline):
    model = BookAuthor
    extra = 1


class BookCategoryInline(admin.TabularInline):
    model = BookCategory
    extra = 1


@admin.register(Reader)
class ReaderAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'user', 'phone', 'registration_date')
    search_fields = ('full_name', 'phone', 'user__username', 'user__email')
    list_filter = ('registration_date',)


@admin.register(Author)
class AuthorAdmin(admin.ModelAdmin):
    list_display = ('full_name',)
    search_fields = ('full_name',)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)


@admin.register(Book)
class BookAdmin(admin.ModelAdmin):
    list_display = (
        'title',
        'authors_display',
        'publication_year',
        'volume_composition',
        'total_copies',
        'available_copies',
    )
    search_fields = ('title', 'authors__full_name')
    list_filter = ('authors', 'categories')
    inlines = [BookAuthorInline, BookCategoryInline]

    @admin.display(description='Авторы')
    def authors_display(self, obj):
        return obj.authors_display()


@admin.register(BookAuthor)
class BookAuthorAdmin(admin.ModelAdmin):
    list_display = ('book', 'author')
    search_fields = ('book__title', 'author__full_name')


@admin.register(BookCategory)
class BookCategoryAdmin(admin.ModelAdmin):
    list_display = ('book', 'category')
    search_fields = ('book__title', 'category__name')


@admin.register(Loan)
class LoanAdmin(admin.ModelAdmin):
    list_display = ('book', 'reader', 'issue_date', 'due_date', 'return_date', 'status')
    search_fields = ('book__title', 'reader__full_name')
    list_filter = ('status', 'issue_date', 'due_date')