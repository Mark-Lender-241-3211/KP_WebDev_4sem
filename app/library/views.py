import csv
from collections import OrderedDict

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group
from django.contrib.auth.views import LoginView
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncMonth
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_date

from .forms import BookForm, LoanForm, ReaderForm, ReaderRegistrationForm
from .models import Book, Category, Loan, Reader


def user_is_librarian(user):
    return (
        user.is_authenticated
        and user.groups.filter(name='Библиотекарь').exists()
    )


def update_overdue_loans():
    today = timezone.localdate()

    Loan.objects.filter(
        status=Loan.STATUS_ISSUED,
        due_date__lt=today,
    ).update(status=Loan.STATUS_OVERDUE)


def build_pagination_query(request):
    params = request.GET.copy()
    params.pop('page', None)

    encoded = params.urlencode()
    return f'&{encoded}' if encoded else ''


def build_sort_links(request, fields, current_sort, current_direction):
    links = {}

    for field in fields:
        params = request.GET.copy()
        params.pop('page', None)

        if current_sort == field and current_direction == 'asc':
            next_direction = 'desc'
        else:
            next_direction = 'asc'

        params['sort'] = field
        params['direction'] = next_direction

        if current_sort == field:
            arrow = '↑' if current_direction == 'asc' else '↓'
        else:
            arrow = '↕'

        links[field] = {
            'url': '?' + params.urlencode(),
            'arrow': arrow,
        }

    return links


def normalize_direction(direction):
    return direction if direction in ['asc', 'desc'] else 'asc'


def get_authors_text(book):
    authors = list(book.authors.all())

    if not authors:
        return 'Авторы не указаны'

    return ', '.join(author.full_name for author in authors)


def get_author_ids(book):
    return tuple(sorted(author.id for author in book.authors.all()))


def choose_primary_book(editions):
    available_books = [
        edition['book']
        for edition in editions
        if edition['book'].available_copies > 0
    ]

    candidates = available_books or [edition['book'] for edition in editions]

    return max(
        candidates,
        key=lambda book: (book.publication_year or 0, book.id),
    )


class LibraryLoginView(LoginView):
    template_name = 'library/login.html'

    def form_invalid(self, form):
        attempts = self.request.session.get('login_attempts', 0)
        self.request.session['login_attempts'] = attempts + 1
        return super().form_invalid(form)

    def form_valid(self, form):
        self.request.session['login_attempts'] = 0
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        attempts = self.request.session.get('login_attempts', 0)
        context['show_password_reset'] = attempts >= 1
        return context


def register(request):
    if request.method == 'POST':
        form = ReaderRegistrationForm(request.POST)

        if form.is_valid():
            user = form.save()

            reader_group, _ = Group.objects.get_or_create(name='Читатель')
            user.groups.add(reader_group)

            login(request, user)
            return redirect('library:home')
    else:
        form = ReaderRegistrationForm()

    return render(request, 'library/register.html', {'form': form})


def home(request):
    return render(request, 'library/home.html')


def catalog(request):
    books = Book.objects.prefetch_related('authors', 'categories')

    query = request.GET.get('q', '').strip()
    author = request.GET.get('author', '').strip()
    category_id = request.GET.get('category', '').strip()
    availability = request.GET.get('availability', '').strip()
    sort = request.GET.get('sort', 'title')
    direction = normalize_direction(request.GET.get('direction', 'asc'))

    if sort not in ['title', 'author', 'category', 'editions', 'available']:
        sort = 'title'

    if query:
        books = books.filter(title__icontains=query)

    if author:
        books = books.filter(authors__full_name__icontains=author)

    if category_id:
        books = books.filter(categories__id=category_id)

    if availability == 'available':
        books = books.filter(available_copies__gt=0)

    books = list(
        books
        .distinct()
        .order_by('title', '-publication_year')
    )

    groups = OrderedDict()

    for book in books:
        authors = list(book.authors.all())
        author_ids = tuple(sorted(author_item.id for author_item in authors))
        authors_text = get_authors_text(book)
        key = (book.title, author_ids)

        if key not in groups:
            groups[key] = {
                'title': book.title,
                'authors': authors,
                'authors_text': authors_text,
                'editions': [],
                'total_copies': 0,
                'available_copies': 0,
                'categories': {},
            }

        category_items = list(book.categories.all())

        groups[key]['editions'].append({
            'book': book,
            'authors': authors,
            'authors_text': authors_text,
            'categories': category_items,
            'category_names': ', '.join(category.name for category in category_items),
        })
        groups[key]['total_copies'] += book.total_copies
        groups[key]['available_copies'] += book.available_copies

        for category in category_items:
            groups[key]['categories'][category.id] = category

    catalog_groups = []

    for index, group in enumerate(groups.values(), start=1):
        categories = sorted(
            group['categories'].values(),
            key=lambda category: category.name.lower(),
        )

        visible_categories = categories[:2]
        hidden_categories_count = max(len(categories) - len(visible_categories), 0)
        category_text = ', '.join(category.name for category in categories)

        group['index'] = index
        group['categories_list'] = categories
        group['visible_categories'] = visible_categories
        group['hidden_categories_count'] = hidden_categories_count
        group['category_text'] = category_text
        group['editions_count'] = len(group['editions'])
        group['primary_book'] = choose_primary_book(group['editions'])

        catalog_groups.append(group)

    reverse = direction == 'desc'

    if sort == 'author':
        catalog_groups.sort(
            key=lambda group: group['authors_text'].lower(),
            reverse=reverse,
        )
    elif sort == 'category':
        catalog_groups.sort(
            key=lambda group: group['category_text'].lower(),
            reverse=reverse,
        )
    elif sort == 'editions':
        catalog_groups.sort(
            key=lambda group: group['editions_count'],
            reverse=reverse,
        )
    elif sort == 'available':
        catalog_groups.sort(
            key=lambda group: group['available_copies'],
            reverse=reverse,
        )
    else:
        catalog_groups.sort(
            key=lambda group: group['title'].lower(),
            reverse=reverse,
        )

    paginator = Paginator(catalog_groups, 10)
    page_obj = paginator.get_page(request.GET.get('page'))

    context = {
        'groups': page_obj.object_list,
        'page_obj': page_obj,
        'pagination_query': build_pagination_query(request),
        'categories': Category.objects.order_by('name'),
        'selected_category': category_id,
        'query': query,
        'author': author,
        'availability': availability,
        'sort': sort,
        'direction': direction,
        'sort_links': build_sort_links(
            request,
            ['title', 'author', 'category', 'editions', 'available'],
            sort,
            direction,
        ),
    }

    return render(request, 'library/catalog.html', context)


def book_detail(request, pk):
    update_overdue_loans()

    book = get_object_or_404(
        Book.objects.prefetch_related('authors', 'categories'),
        pk=pk,
    )

    current_author_ids = get_author_ids(book)

    editions = (
        Book.objects
        .prefetch_related('authors', 'categories')
        .filter(title=book.title)
        .exclude(pk=book.pk)
        .order_by('publication_year')
    )

    other_editions = [
        edition for edition in editions
        if get_author_ids(edition) == current_author_ids
    ]

    active_book_loans = (
        Loan.objects
        .select_related('reader')
        .filter(
            book=book,
            status__in=[Loan.STATUS_ISSUED, Loan.STATUS_OVERDUE],
        )
        .order_by('due_date', 'issue_date')
    )

    return render(request, 'library/book_detail.html', {
        'book': book,
        'authors_text': get_authors_text(book),
        'other_editions': other_editions,
        'active_book_loans': active_book_loans,
    })


@login_required
def loans(request):
    if not user_is_librarian(request.user):
        return redirect('library:catalog')

    update_overdue_loans()

    loans_list = Loan.objects.select_related('book', 'reader')

    status = request.GET.get('status', '').strip()
    query = request.GET.get('q', '').strip()
    sort = request.GET.get('sort', 'issue_date')
    direction = normalize_direction(request.GET.get('direction', 'desc'))

    if sort not in ['book', 'reader', 'issue_date', 'due_date', 'return_date', 'status']:
        sort = 'issue_date'

    if status:
        loans_list = loans_list.filter(status=status)

    if query:
        loans_list = loans_list.filter(
            Q(book__title__icontains=query)
            | Q(book__volume_composition__icontains=query)
            | Q(reader__full_name__icontains=query)
        )

    sort_fields = {
        'book': 'book__title',
        'reader': 'reader__full_name',
        'issue_date': 'issue_date',
        'due_date': 'due_date',
        'return_date': 'return_date',
        'status': 'status',
    }

    order_field = sort_fields[sort]
    if direction == 'desc':
        order_field = '-' + order_field

    loans_list = loans_list.order_by(order_field)

    paginator = Paginator(loans_list, 10)
    page_obj = paginator.get_page(request.GET.get('page'))

    context = {
        'loans': page_obj.object_list,
        'page_obj': page_obj,
        'pagination_query': build_pagination_query(request),
        'status': status,
        'query': query,
        'status_choices': Loan.STATUS_CHOICES,
        'is_staff_user': True,
        'sort': sort,
        'direction': direction,
        'sort_links': build_sort_links(
            request,
            ['book', 'reader', 'issue_date', 'due_date', 'return_date', 'status'],
            sort,
            direction,
        ),
    }

    return render(request, 'library/loans.html', context)


@login_required
def readers(request):
    if not user_is_librarian(request.user):
        return redirect('library:catalog')

    query = request.GET.get('q', '').strip()

    readers_list = Reader.objects.select_related('user').order_by('full_name')

    if query:
        readers_list = readers_list.filter(
            Q(full_name__icontains=query)
            | Q(phone__icontains=query)
            | Q(user__email__icontains=query)
            | Q(user__username__icontains=query)
        )

    return render(request, 'library/readers.html', {
        'readers': readers_list,
        'query': query,
    })


@login_required
def update_reader(request, pk):
    if not user_is_librarian(request.user):
        return redirect('library:catalog')

    reader = get_object_or_404(
        Reader.objects.select_related('user'),
        pk=pk,
    )

    if request.method == 'POST':
        form = ReaderForm(request.POST, instance=reader)

        if form.is_valid():
            form.save()
            messages.success(request, 'Данные читателя обновлены.')
            return redirect('library:reader_detail', pk=reader.pk)
    else:
        form = ReaderForm(instance=reader)

    return render(request, 'library/reader_form.html', {
        'form': form,
        'reader': reader,
    })


@login_required
def reader_detail(request, pk):
    if not user_is_librarian(request.user):
        return redirect('library:catalog')

    reader = get_object_or_404(
        Reader.objects.select_related('user'),
        pk=pk,
    )

    reader_loans = (
        Loan.objects
        .select_related('book')
        .filter(reader=reader)
        .order_by('-issue_date')
    )

    return render(request, 'library/reader_detail.html', {
        'reader': reader,
        'reader_loans': reader_loans,
    })


@login_required
def create_book(request):
    if not user_is_librarian(request.user):
        return redirect('library:catalog')

    if request.method == 'POST':
        form = BookForm(request.POST, request.FILES)

        if form.is_valid():
            book = form.save()
            messages.success(request, 'Книга добавлена.')
            return redirect('library:book_detail', pk=book.pk)
    else:
        form = BookForm()

    return render(request, 'library/book_form.html', {
        'form': form,
        'page_title': 'Добавление книги',
        'submit_text': 'Добавить книгу',
    })


@login_required
def update_book(request, pk):
    if not user_is_librarian(request.user):
        return redirect('library:catalog')

    book = get_object_or_404(
        Book.objects.prefetch_related('authors', 'categories'),
        pk=pk,
    )

    if request.method == 'POST':
        form = BookForm(request.POST, request.FILES, instance=book)

        if form.is_valid():
            book = form.save()
            messages.success(request, 'Книга обновлена.')
            return redirect('library:book_detail', pk=book.pk)
    else:
        form = BookForm(instance=book)

    return render(request, 'library/book_form.html', {
        'form': form,
        'book': book,
        'page_title': 'Редактирование книги',
        'submit_text': 'Сохранить изменения',
    })


@login_required
def delete_book(request, pk):
    if not user_is_librarian(request.user):
        return redirect('library:catalog')

    book = get_object_or_404(Book, pk=pk)

    if request.method == 'POST':
        if book.loans.exists():
            messages.error(
                request,
                'Нельзя удалить книгу, по которой уже есть записи о выдачах.'
            )
            return redirect('library:book_detail', pk=book.pk)

        book.delete()
        messages.success(request, 'Книга удалена.')
        return redirect('library:catalog')

    return render(request, 'library/book_confirm_delete.html', {
        'book': book,
    })


@login_required
def create_loan(request):
    if not user_is_librarian(request.user):
        return redirect('library:catalog')

    if request.method == 'POST':
        form = LoanForm(request.POST)

        if form.is_valid():
            with transaction.atomic():
                loan = form.save(commit=False)
                loan.status = Loan.STATUS_ISSUED
                loan.save()

                book = loan.book
                book.available_copies -= 1
                book.save(update_fields=['available_copies'])

            return redirect('library:loans')
    else:
        initial = {}

        book_id = request.GET.get('book')
        if book_id:
            initial['book'] = book_id

        form = LoanForm(initial=initial)

    return render(request, 'library/loan_form.html', {'form': form})


@login_required
def return_loan(request, pk):
    if not user_is_librarian(request.user):
        return redirect('library:catalog')

    loan = get_object_or_404(
        Loan.objects.select_related('book'),
        pk=pk,
    )

    if request.method == 'POST' and loan.status != Loan.STATUS_RETURNED:
        with transaction.atomic():
            loan.status = Loan.STATUS_RETURNED
            loan.return_date = timezone.localdate()
            loan.save(update_fields=['status', 'return_date'])

            book = loan.book
            if book.available_copies < book.total_copies:
                book.available_copies += 1
                book.save(update_fields=['available_copies'])

    return redirect('library:loans')


@login_required
def statistics(request):
    if not user_is_librarian(request.user):
        return redirect('library:catalog')

    update_overdue_loans()

    today = timezone.localdate()
    first_day_of_month = today.replace(day=1)

    date_from_raw = request.GET.get('date_from', '').strip()
    date_to_raw = request.GET.get('date_to', '').strip()
    selected_category = request.GET.get('category', '').strip()
    category_sort = request.GET.get('category_sort', 'books')

    date_from = parse_date(date_from_raw) if date_from_raw else first_day_of_month
    date_to = parse_date(date_to_raw) if date_to_raw else today

    if date_from is None:
        date_from = first_day_of_month

    if date_to is None:
        date_to = today

    if date_to < date_from:
        date_from, date_to = date_to, date_from

    date_from_raw = date_from.strftime('%Y-%m-%d')
    date_to_raw = date_to.strftime('%Y-%m-%d')

    filtered_loans = (
        Loan.objects
        .select_related('book', 'reader')
        .prefetch_related('book__categories')
        .filter(issue_date__gte=date_from, issue_date__lte=date_to)
    )

    if selected_category:
        filtered_loans = filtered_loans.filter(book__categories__id=selected_category)

    filtered_loans = filtered_loans.distinct()

    books_count = Book.objects.count()

    readers_with_books = Reader.objects.filter(
        loans__issue_date__lte=date_to,
    ).filter(
        Q(loans__return_date__isnull=True)
        | Q(loans__return_date__gte=date_from)
    )

    if selected_category:
        readers_with_books = readers_with_books.filter(
            loans__book__categories__id=selected_category
        )

    readers_count = readers_with_books.distinct().count()

    total_loans_count = filtered_loans.count()

    active_loans_count = filtered_loans.filter(
        status__in=[Loan.STATUS_ISSUED, Loan.STATUS_OVERDUE]
    ).count()

    overdue_loans_count = filtered_loans.filter(
        status=Loan.STATUS_OVERDUE
    ).count()

    copies_summary = Book.objects.aggregate(
        total_copies=Sum('total_copies'),
        available_copies=Sum('available_copies'),
    )

    total_copies = copies_summary['total_copies'] or 0
    available_copies = copies_summary['available_copies'] or 0
    issued_copies = total_copies - available_copies

    category_loan_filter = Q(
        books__loans__issue_date__gte=date_from,
        books__loans__issue_date__lte=date_to,
    )

    active_category_loan_filter = category_loan_filter & Q(
        books__loans__status__in=[
            Loan.STATUS_ISSUED,
            Loan.STATUS_OVERDUE,
        ]
    )

    popular_categories = (
        Category.objects
        .annotate(
            books_count=Count('books', distinct=True),
            active_loans_count=Count(
                'books__loans',
                filter=active_category_loan_filter,
                distinct=True,
            ),
            total_loans_count=Count(
                'books__loans',
                filter=category_loan_filter,
                distinct=True,
            ),
        )
        .filter(books_count__gt=0)
    )

    if selected_category:
        popular_categories = popular_categories.filter(id=selected_category)

    if category_sort == 'active_loans':
        popular_categories = popular_categories.order_by(
            '-active_loans_count',
            'name',
        )
    elif category_sort == 'total_loans':
        popular_categories = popular_categories.order_by(
            '-total_loans_count',
            'name',
        )
    elif category_sort == 'name':
        popular_categories = popular_categories.order_by('name')
    else:
        popular_categories = popular_categories.order_by(
            '-books_count',
            'name',
        )

    popular_categories = popular_categories[:5]

    monthly_rows = (
        filtered_loans
        .annotate(month=TruncMonth('issue_date'))
        .values('month')
        .annotate(count=Count('id'))
        .order_by('month')
    )

    monthly_stats = [
        {
            'month': row['month'].strftime('%m.%Y') if row['month'] else '',
            'count': row['count'],
        }
        for row in monthly_rows
    ]

    max_monthly_count = max(
        [item['count'] for item in monthly_stats],
        default=0,
    )

    for item in monthly_stats:
        item['height_percent'] = (
            int(item['count'] / max_monthly_count * 100)
            if max_monthly_count
            else 0
        )

    recent_loans = filtered_loans.order_by('-issue_date')[:5]

    context = {
        'books_count': books_count,
        'readers_count': readers_count,
        'total_loans_count': total_loans_count,
        'active_loans_count': active_loans_count,
        'overdue_loans_count': overdue_loans_count,
        'total_copies': total_copies,
        'available_copies': available_copies,
        'issued_copies': issued_copies,
        'popular_categories': popular_categories,
        'recent_loans': recent_loans,
        'monthly_stats': monthly_stats,
        'categories': Category.objects.order_by('name'),
        'selected_category': selected_category,
        'category_sort': category_sort,
        'date_from': date_from_raw,
        'date_to': date_to_raw,
    }

    return render(request, 'library/statistics.html', context)


@login_required
def export_books_csv(request):
    if not user_is_librarian(request.user):
        return redirect('library:catalog')

    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="books.csv"'

    response.write('\ufeff')

    writer = csv.writer(response, delimiter=';')
    writer.writerow([
        'Название',
        'Авторы',
        'Категории',
        'Год издания',
        'Состав томов',
        'Всего экземпляров',
        'Доступно экземпляров',
        'Описание',
    ])

    books = (
        Book.objects
        .prefetch_related('authors', 'categories')
        .order_by('title', '-publication_year')
    )

    for book in books:
        authors = ', '.join(author.full_name for author in book.authors.all())
        categories = ', '.join(category.name for category in book.categories.all())

        writer.writerow([
            book.title,
            authors,
            categories,
            book.publication_year or '',
            book.volume_composition,
            book.total_copies,
            book.available_copies,
            book.description,
        ])

    return response


@login_required
def export_loans_csv(request):
    if not user_is_librarian(request.user):
        return redirect('library:catalog')

    update_overdue_loans()

    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="loans.csv"'

    response.write('\ufeff')

    writer = csv.writer(response, delimiter=';')
    writer.writerow([
        'Книга',
        'Издание',
        'Читатель',
        'Дата выдачи',
        'Срок возврата',
        'Дата возврата',
        'Статус',
    ])

    loans = (
        Loan.objects
        .select_related('book', 'reader')
        .order_by('-issue_date')
    )

    for loan in loans:
        writer.writerow([
            loan.book.title,
            loan.book.edition_display(),
            loan.reader.full_name,
            loan.issue_date.strftime('%d.%m.%Y') if loan.issue_date else '',
            loan.due_date.strftime('%d.%m.%Y') if loan.due_date else '',
            loan.return_date.strftime('%d.%m.%Y') if loan.return_date else '',
            loan.get_status_display(),
        ])

    return response