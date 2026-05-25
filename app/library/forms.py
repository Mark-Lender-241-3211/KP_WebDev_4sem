from datetime import timedelta

from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.utils import timezone

from .models import (
    Author,
    Book,
    BookAuthor,
    BookCategory,
    Category,
    Loan,
    Reader,
    normalize_phone_number,
)


class ReaderRegistrationForm(UserCreationForm):
    email = forms.EmailField(label='Электронная почта', required=True)
    full_name = forms.CharField(label='ФИО', max_length=255)
    phone = forms.CharField(label='Телефон', max_length=20, required=False)

    class Meta:
        model = User
        fields = ('username', 'email', 'full_name', 'phone', 'password1', 'password2')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for field in self.fields.values():
            field.widget.attrs.update({'class': 'form-control'})

    def clean_phone(self):
        return normalize_phone_number(self.cleaned_data.get('phone', ''))

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']

        if commit:
            user.save()

            Reader.objects.create(
                user=user,
                full_name=self.cleaned_data['full_name'],
                phone=self.cleaned_data.get('phone', ''),
            )

        return user


class BookChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        authors = obj.authors_display()
        year = obj.publication_year if obj.publication_year else 'год не указан'
        composition = obj.volume_composition.strip()

        title = obj.title
        if len(title) > 36:
            title = title[:33] + '...'

        if len(authors) > 28:
            authors = authors[:25] + '...'

        if len(composition) > 24:
            composition = composition[:21] + '...'

        composition_part = f', {composition}' if composition else ''

        return (
            f'{title}, {year}{composition_part} — '
            f'{obj.available_copies} из {obj.total_copies} — {authors}'
        )


class LoanForm(forms.ModelForm):
    book = BookChoiceField(
        queryset=Book.objects.none(),
        label='Книга',
        empty_label='Выберите книгу',
    )

    reader = forms.ModelChoiceField(
        queryset=Reader.objects.none(),
        label='Читатель',
        empty_label='Выберите читателя',
    )

    class Meta:
        model = Loan
        fields = ('book', 'reader', 'issue_date', 'due_date')
        widgets = {
            'issue_date': forms.DateInput(
                format='%Y-%m-%d',
                attrs={'type': 'date'},
            ),
            'due_date': forms.DateInput(
                format='%Y-%m-%d',
                attrs={'type': 'date'},
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        today = timezone.localdate()
        due_date = today + timedelta(days=30)

        self.fields['book'].queryset = (
            Book.objects
            .filter(available_copies__gt=0)
            .prefetch_related('authors')
            .order_by('title', '-publication_year')
        )

        self.fields['reader'].queryset = Reader.objects.order_by('full_name')

        self.fields['issue_date'].initial = today.strftime('%Y-%m-%d')
        self.fields['due_date'].initial = due_date.strftime('%Y-%m-%d')

        for field in self.fields.values():
            field.widget.attrs.update({'class': 'form-control'})

    def clean_book(self):
        book = self.cleaned_data['book']

        if book.available_copies <= 0:
            raise forms.ValidationError('Нет доступных экземпляров этой книги.')

        return book

    def clean(self):
        cleaned_data = super().clean()

        issue_date = cleaned_data.get('issue_date')
        due_date = cleaned_data.get('due_date')

        if issue_date and due_date and due_date < issue_date:
            raise forms.ValidationError(
                'Срок возврата не может быть раньше даты выдачи.'
            )

        return cleaned_data


class BookForm(forms.ModelForm):
    authors = forms.ModelMultipleChoiceField(
        queryset=Author.objects.order_by('full_name'),
        label='Авторы',
        required=False,
    )

    categories = forms.ModelMultipleChoiceField(
        queryset=Category.objects.order_by('name'),
        label='Категории',
        required=False,
    )

    class Meta:
        model = Book
        fields = (
            'title',
            'authors',
            'categories',
            'publication_year',
            'volume_composition',
            'description',
            'total_copies',
            'available_copies',
            'cover',
        )
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if self.instance and self.instance.pk:
            self.fields['authors'].initial = self.instance.authors.all()
            self.fields['categories'].initial = self.instance.categories.all()

        for field in self.fields.values():
            if isinstance(field.widget, forms.SelectMultiple):
                field.widget.attrs.update({'class': 'form-select'})
            else:
                field.widget.attrs.update({'class': 'form-control'})

    def clean(self):
        cleaned_data = super().clean()

        total_copies = cleaned_data.get('total_copies')
        available_copies = cleaned_data.get('available_copies')

        if (
            total_copies is not None
            and available_copies is not None
            and available_copies > total_copies
        ):
            raise forms.ValidationError(
                'Количество доступных экземпляров не может быть больше общего количества.'
            )

        return cleaned_data

    def save(self, commit=True):
        book = super().save(commit=False)

        if commit:
            book.save()

            BookAuthor.objects.filter(book=book).delete()
            BookCategory.objects.filter(book=book).delete()

            BookAuthor.objects.bulk_create([
                BookAuthor(book=book, author=author)
                for author in self.cleaned_data['authors']
            ])

            BookCategory.objects.bulk_create([
                BookCategory(book=book, category=category)
                for category in self.cleaned_data['categories']
            ])

        return book

class AuthorForm(forms.ModelForm):
    class Meta:
        model = Author
        fields = ('full_name', 'description')
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for field in self.fields.values():
            field.widget.attrs.update({'class': 'form-control'})


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ('name', 'description')
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for field in self.fields.values():
            field.widget.attrs.update({'class': 'form-control'})

class ReaderForm(forms.ModelForm):
    email = forms.EmailField(
        label='Электронная почта',
        required=False,
    )

    class Meta:
        model = Reader
        fields = ('full_name', 'phone', 'email')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if self.instance and self.instance.pk and self.instance.user:
            self.fields['email'].initial = self.instance.user.email

        for field in self.fields.values():
            field.widget.attrs.update({'class': 'form-control'})

    def clean_phone(self):
        return normalize_phone_number(self.cleaned_data.get('phone', ''))

    def save(self, commit=True):
        reader = super().save(commit=False)

        if commit:
            reader.save()

            if reader.user:
                reader.user.email = self.cleaned_data.get('email', '')
                reader.user.save(update_fields=['email'])

        return reader