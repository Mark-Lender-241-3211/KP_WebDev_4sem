from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models

def normalize_phone_number(phone):
    if not phone:
        return ''

    digits = ''.join(char for char in phone if char.isdigit())

    if len(digits) == 10:
        digits = '7' + digits

    if len(digits) == 11 and digits.startswith('8'):
        digits = '7' + digits[1:]

    if len(digits) != 11 or not digits.startswith('7'):
        raise ValidationError(
            'Введите российский номер телефона в формате +7XXXXXXXXXX или 8XXXXXXXXXX.'
        )

    return (
        f'+7 ({digits[1:4]}) '
        f'{digits[4:7]}-'
        f'{digits[7:9]}-'
        f'{digits[9:11]}'
    )

class Reader(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='reader_profile',
        verbose_name='Пользователь',
    )
    full_name = models.CharField('ФИО', max_length=255)
    phone = models.CharField('Телефон', max_length=20, blank=True)
    registration_date = models.DateField('Дата регистрации', auto_now_add=True)

    def clean(self):
        self.phone = normalize_phone_number(self.phone)

    def save(self, *args, **kwargs):
        self.phone = normalize_phone_number(self.phone)
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = 'читатель'
        verbose_name_plural = 'читатели'
        ordering = ['full_name']

    def __str__(self):
        return self.full_name


class Author(models.Model):
    full_name = models.CharField('ФИО автора или название коллектива', max_length=255)
    description = models.TextField('Описание', blank=True)

    class Meta:
        verbose_name = 'автор'
        verbose_name_plural = 'авторы'
        ordering = ['full_name']

    def __str__(self):
        return self.full_name


class Category(models.Model):
    name = models.CharField('Название категории', max_length=100, unique=True)
    description = models.TextField('Описание', blank=True)

    class Meta:
        verbose_name = 'категория'
        verbose_name_plural = 'категории'
        ordering = ['name']

    def __str__(self):
        return self.name


class Book(models.Model):
    title = models.CharField('Название', max_length=255)

    authors = models.ManyToManyField(
        Author,
        through='BookAuthor',
        related_name='books',
        verbose_name='Авторы',
        blank=True,
    )

    categories = models.ManyToManyField(
        Category,
        through='BookCategory',
        related_name='books',
        verbose_name='Категории',
        blank=True,
    )

    publication_year = models.PositiveIntegerField(
        'Год издания',
        null=True,
        blank=True,
    )

    volume_composition = models.CharField(
        'Состав томов',
        max_length=255,
        blank=True,
        default='',
    )

    description = models.TextField('Описание', blank=True)
    total_copies = models.PositiveIntegerField('Всего экземпляров', default=1)
    available_copies = models.PositiveIntegerField('Доступно экземпляров', default=1)
    cover = models.FileField('Обложка', upload_to='covers/', blank=True, null=True)

    class Meta:
        verbose_name = 'книга'
        verbose_name_plural = 'книги'
        ordering = ['title']

    def clean(self):
        if self.available_copies > self.total_copies:
            raise ValidationError(
                'Количество доступных экземпляров не может быть больше общего количества.'
            )

    def authors_display(self):
        authors = self.authors.all()
        if not authors:
            return 'Авторы не указаны'
        return ', '.join(author.full_name for author in authors)

    def edition_display(self):
        parts = []

        if self.publication_year:
            parts.append(str(self.publication_year))

        if self.volume_composition:
            parts.append(self.volume_composition)

        return ', '.join(parts) if parts else 'издание не указано'

    def __str__(self):
        return self.title


class BookAuthor(models.Model):
    book = models.ForeignKey(
        Book,
        on_delete=models.CASCADE,
        related_name='book_authors',
        verbose_name='Книга',
    )
    author = models.ForeignKey(
        Author,
        on_delete=models.CASCADE,
        related_name='book_authors',
        verbose_name='Автор',
    )

    class Meta:
        verbose_name = 'связь книги и автора'
        verbose_name_plural = 'связи книг и авторов'
        unique_together = ('book', 'author')

    def __str__(self):
        return f'{self.book} — {self.author}'


class BookCategory(models.Model):
    book = models.ForeignKey(
        Book,
        on_delete=models.CASCADE,
        related_name='book_categories',
        verbose_name='Книга',
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.CASCADE,
        related_name='book_categories',
        verbose_name='Категория',
    )

    class Meta:
        verbose_name = 'связь книги и категории'
        verbose_name_plural = 'связи книг и категорий'
        unique_together = ('book', 'category')

    def __str__(self):
        return f'{self.book} — {self.category}'


class Loan(models.Model):
    STATUS_ISSUED = 'issued'
    STATUS_RETURNED = 'returned'
    STATUS_OVERDUE = 'overdue'

    STATUS_CHOICES = [
        (STATUS_ISSUED, 'Выдана'),
        (STATUS_RETURNED, 'Возвращена'),
        (STATUS_OVERDUE, 'Просрочена'),
    ]

    book = models.ForeignKey(
        Book,
        on_delete=models.PROTECT,
        related_name='loans',
        verbose_name='Книга',
    )
    reader = models.ForeignKey(
        Reader,
        on_delete=models.PROTECT,
        related_name='loans',
        verbose_name='Читатель',
    )
    issue_date = models.DateField('Дата выдачи')
    due_date = models.DateField('Плановая дата возврата')
    return_date = models.DateField('Фактическая дата возврата', null=True, blank=True)
    status = models.CharField(
        'Статус',
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_ISSUED,
    )

    class Meta:
        verbose_name = 'выдача'
        verbose_name_plural = 'выдачи'
        ordering = ['-issue_date']

    def clean(self):
        if self.due_date and self.issue_date and self.due_date < self.issue_date:
            raise ValidationError('Плановая дата возврата не может быть раньше даты выдачи.')

        if self.return_date and self.issue_date and self.return_date < self.issue_date:
            raise ValidationError('Фактическая дата возврата не может быть раньше даты выдачи.')

    def __str__(self):
        return f'{self.book} — {self.reader}'