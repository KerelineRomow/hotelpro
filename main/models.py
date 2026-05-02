from django.db import models
from django.utils.text import slugify
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta
from django.db.models import Q
from django.core.validators import RegexValidator


class Room(models.Model):
    number = models.CharField("Назва або номер кімнати", max_length=70, unique=True)
    slug = models.SlugField("URL-адреса (slug)", max_length=100, unique=True, blank=True)
    description = models.TextField("Опис", blank=True)
    base_price = models.DecimalField("Базова ціна за ніч", max_digits=10, decimal_places=2)
    is_active = models.BooleanField("Активний (доступний для броні)", default=True)
    image = models.ImageField("Головне фото номера", upload_to="rooms/", blank=True)
    beds_count = models.PositiveIntegerField("Кількість ліжок", default=1)

    has_bath = models.BooleanField("Власний санвузол", default=False)
    has_wifi = models.BooleanField("Безкоштовний Wi-Fi", default=True)
    has_tv = models.BooleanField("Телевізор", default=False)
    has_fridge = models.BooleanField("Холодильник", default=False)
    has_kettle = models.BooleanField("Електрочайник", default=True)
    has_ac = models.BooleanField("Вентилятор/Кондиціонер", default=False)

    def save(self, *args, **kwargs):
        if not self.slug or (self.pk is not None and self.number != Room.objects.get(pk=self.pk).number):
            self.slug = slugify(self.number, allow_unicode=True)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('room_detail', kwargs={'slug': self.slug})

    def __str__(self):
        return self.number

    class Meta:
        verbose_name = "Номер"
        verbose_name_plural = "Номери"
        ordering = ['number']


class RoomPrice(models.Model):
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='prices', verbose_name="Кімната")
    guests_count = models.PositiveIntegerField("Кількість осіб")
    price = models.DecimalField("Вартість", max_digits=10, decimal_places=2)

    class Meta:
        verbose_name = "Ціна за кількість осіб"
        verbose_name_plural = "Динамічні ціни"
        unique_together = ('room', 'guests_count')
        ordering = ['guests_count']


class RoomImage(models.Model):
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='images', verbose_name="Номер")
    image = models.ImageField("Додаткове фото", upload_to="rooms/gallery/")

    class Meta:
        verbose_name = "Фото номера"
        verbose_name_plural = "Галерея фото"


class CustomerProfile(models.Model):
    first_name = models.CharField("Ім'я", max_length=100)
    last_name = models.CharField("Прізвище", max_length=100)
    phone = models.CharField("Телефон", max_length=20, unique=True)
    admin_note = models.TextField("Нотатки адміністратора (нюанси/репутація)", blank=True)

    class Meta:
        verbose_name = "Профіль клієнта"
        verbose_name_plural = "Історія та Клієнти"

    def __str__(self):
        return f"{self.last_name} {self.first_name} ({self.phone})"


class BookingRequest(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Очікує підтвердження'),
        ('confirmed', 'Підтверджено'),
        ('canceled', 'Скасовано'),
    ]
    room = models.ForeignKey(Room, on_delete=models.SET_NULL, null=True, verbose_name="Номер")
    customer_name = models.CharField("Ім'я та Прізвище", max_length=200)
    customer_phone = models.CharField("Телефон", max_length=20)
    guests_count = models.PositiveIntegerField("Кількість осіб", default=1)
    check_in = models.DateField("Дата заїзду")
    check_out = models.DateField("Дата виїзду")
    message = models.TextField("Повідомлення/Побажання", blank=True)
    status = models.CharField("Статус", max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        if self.check_in >= self.check_out:
            raise ValidationError("Дата виїзду має бути пізніше дати заїзду")

    class Meta:
        verbose_name = "Запит на бронювання"
        verbose_name_plural = "Запити на бронювання"
        ordering = ['-created_at']


class Booking(models.Model):
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='bookings_confirmed', verbose_name="Номер")
    customer_profile = models.ForeignKey(CustomerProfile, on_delete=models.CASCADE, verbose_name="Клієнт", null=True)
    guests_count = models.PositiveIntegerField("Кількість осіб", default=1)
    check_in = models.DateField("Дата заїзду")
    check_out = models.DateField("Дата виїзду")
    comment = models.TextField("Коментар до цієї броні", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        if self.check_in >= self.check_out:
            raise ValidationError("Дата виїзду має бути пізніше дати заїзду")

    class Meta:
        verbose_name = "Підтверджене бронювання"
        verbose_name_plural = "Журнал бронювань"
        indexes = [
            models.Index(fields=['check_in', 'check_out']),
            models.Index(fields=['room', 'check_in', 'check_out']),
        ]
        ordering = ['-check_in']


class CallbackRequest(models.Model):
    name = models.CharField("Ім'я", max_length=30)

    phone_regex = RegexValidator(
        regex=r'^\+?1?\d{9,15}$',
        message="Номер телефону має бути в форматі: '+999999999'. Тільки цифри."
    )
    phone = models.CharField("Телефон", validators=[phone_regex], max_length=20)

    email = models.EmailField("Email")
    message = models.TextField("Повідомлення")
    created_at = models.DateTimeField("Дата запиту", auto_now_add=True)
    is_processed = models.BooleanField("Опрацьовано", default=False)

    class Meta:
        verbose_name = "Запит на дзвінок"
        verbose_name_plural = "Запити на дзвінки"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} ({self.phone})"

    @staticmethod
    def is_spam(name: str, phone: str) -> bool:
        half_hour_ago = timezone.now() - timedelta(minutes=30)
        return CallbackRequest.objects.filter(
            (Q(name__iexact=name) | Q(phone=phone)),
            created_at__gte=half_hour_ago
        ).exists()
