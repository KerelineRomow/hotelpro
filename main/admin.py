from django.contrib import admin
from django.utils.html import format_html
from django.contrib import messages
from django.urls import path, reverse
from django.http import HttpResponseRedirect
from django.utils.safestring import mark_safe
from django.db import transaction
from django.utils import timezone

from .models import (
    Room, RoomImage, Booking, RoomPrice,
    BookingRequest, CustomerProfile, CallbackRequest
)


APP_LABEL = BookingRequest._meta.app_label


class RoomImageInline(admin.TabularInline):
    model = RoomImage
    extra = 1


class RoomPriceInline(admin.TabularInline):
    model = RoomPrice
    extra = 1


class BookingInline(admin.TabularInline):
    model = Booking
    extra = 0
    readonly_fields = ('check_in', 'check_out', 'guests_count', 'comment')


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    inlines = [RoomPriceInline, RoomImageInline]
    list_display = ('number', 'base_price', 'beds_count', 'is_active')
    list_editable = ('is_active', 'base_price')
    exclude = ('slug',)


@admin.register(CustomerProfile)
class CustomerProfileAdmin(admin.ModelAdmin):
    list_display = ('last_name', 'first_name', 'phone', 'booking_count', 'admin_note')
    search_fields = ('phone', 'last_name')
    inlines = [BookingInline]

    def booking_count(self, obj):
        return obj.booking_set.count()
    booking_count.short_description = 'Кількість бронювань'
    booking_count.admin_order_field = 'booking_count'


@admin.register(BookingRequest)
class BookingRequestAdmin(admin.ModelAdmin):
    list_display = (
        'status_colored',
        'reputation_check',
        'customer_name',
        'customer_phone',
        'guests_count',
        'preliminary_cost',
        'room',
        'check_in',
        'created_at',
    )
    list_filter = ('status', 'created_at', 'room')
    search_fields = ('customer_name', 'customer_phone')

    fieldsets = (
        ('Керування запитом', {
            'fields': ('status', 'manage_booking_buttons', 'reputation_details'),
        }),
        ('Дані клієнта', {
            'fields': (
                'customer_name',
                'customer_phone',
                'guests_count',
                'room',
                ('check_in', 'check_out'),
                'message',
            ),
        }),
    )

    readonly_fields = ('manage_booking_buttons', 'reputation_details')

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('room')

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('<path:object_id>/process/<str:action>/',
                 self.admin_site.admin_view(self.process_booking),
                 name=f'{APP_LABEL}_bookingrequest_process'),
        ]
        return custom_urls + urls

    def process_booking(self, request, object_id, action):
        obj = self.get_object(request, object_id)
        if not obj:
            return HttpResponseRedirect(reverse(f'admin:{APP_LABEL}_bookingrequest_changelist'))

        if action == 'confirm' and obj.status == 'pending':
            if not obj.room:
                self.message_user(request, "Помилка: Номер не вибрано!", messages.ERROR)
            else:
                with transaction.atomic():
                    overlap = Booking.objects.filter(
                        room=obj.room,
                        check_in__lt=obj.check_out,
                        check_out__gt=obj.check_in
                    ).exists()

                    if overlap:
                        self.message_user(request, f"❌ ПОМИЛКА: Номер {obj.room} уже зайнятий!", messages.ERROR)
                    else:
                        try:
                            name_parts = obj.customer_name.strip().split(' ')
                            f_name = name_parts[0]
                            l_name = " ".join(name_parts[1:]) if len(name_parts) > 1 else "—"

                            profile, _ = CustomerProfile.objects.get_or_create(
                                phone=obj.customer_phone.strip(),
                                defaults={'first_name': f_name, 'last_name': l_name}
                            )

                            Booking.objects.create(
                                room=obj.room,
                                customer_profile=profile,
                                guests_count=obj.guests_count,
                                check_in=obj.check_in,
                                check_out=obj.check_out,
                                comment=f"Підтверджено з сайту. {obj.message}"
                            )

                            obj.status = 'confirmed'
                            obj.save()
                            self.message_user(request, f"✅ Бронювання для {obj.customer_name} створено!", messages.SUCCESS)
                        except Exception as e:
                            self.message_user(request, f"Помилка: {str(e)}", messages.ERROR)

        elif action == 'cancel' and obj.status == 'pending':
            obj.status = 'canceled'
            obj.save()
            self.message_user(request, "❌ Запит скасовано.", messages.WARNING)

        return HttpResponseRedirect(reverse(f'admin:{APP_LABEL}_bookingrequest_change', args=[obj.pk]))

    def manage_booking_buttons(self, obj):
        if not obj or not obj.pk:
            return "—"
        if obj.status == 'pending':
            c_url = reverse(f'admin:{APP_LABEL}_bookingrequest_process', args=[obj.pk, 'confirm'])
            x_url = reverse(f'admin:{APP_LABEL}_bookingrequest_process', args=[obj.pk, 'cancel'])
            return format_html(
                '<a class="button" href="{}" style="background:#28a745;color:white;padding:8px 15px;text-decoration:none;border-radius:4px;font-weight:bold;margin-right:10px;">✅ ПІДТВЕРДИТИ</a>'
                '<a class="button" href="{}" style="background:#dc3545;color:white;padding:8px 15px;text-decoration:none;border-radius:4px;font-weight:bold;">❌ СКАСУВАТИ</a>',
                c_url, x_url
            )
        return mark_safe(f"<b>Опрацьовано ({obj.get_status_display()})</b>")

    manage_booking_buttons.short_description = "Швидкі дії"

    def status_colored(self, obj):
        colors = {'pending': 'blue', 'confirmed': 'green', 'canceled': 'red'}
        return format_html('<b style="color:{};">{}</b>', colors.get(obj.status, 'black'), obj.get_status_display())
    status_colored.short_description = "Статус"

    def reputation_check(self, obj):
        if CustomerProfile.objects.filter(phone=obj.customer_phone).exists():
            return mark_safe('<span style="color:blue;">Повторне звернення</span>')
        return mark_safe('<span style="color:green;">Новий клієнт</span>')
    reputation_check.short_description = "Тип"

    def reputation_details(self, obj):
        profile = CustomerProfile.objects.filter(phone=obj.customer_phone).first()
        if profile and profile.admin_note:
            return format_html(
                "<div style='background:rgba(13, 110, 253, 0.05); padding:10px; border-left:4px solid #0d6efd;'>"
                "<b>Нотатки адміністратора:</b><br>{}</div>",
                profile.admin_note
            )
        return "Нотаток немає"
    reputation_details.short_description = "Історія"

    def preliminary_cost(self, obj):
        if not obj.room or not obj.check_in or not obj.check_out:
            return "—"
        days = (obj.check_out - obj.check_in).days
        price_obj = obj.room.prices.filter(guests_count=obj.guests_count).first()
        total = (price_obj.price if price_obj else obj.room.base_price) * days
        return f"{total} грн ({days} ночей × {obj.guests_count} осіб)"
    preliminary_cost.short_description = "Попередня вартість"


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ('room', 'customer_profile', 'guests_count', 'check_in', 'check_out', 'status_colored')
    list_filter = ('check_in', 'check_out', 'room')
    search_fields = ('customer_profile__phone', 'customer_profile__last_name', 'room__number')
    ordering = ['-check_in']

    def status_colored(self, obj):
        today = timezone.now().date()
        if obj.check_out < today:
            color = 'gray'
            text = 'Завершено'
        elif obj.check_in > today:
            color = 'green'
            text = 'Майбутнє'
        else:
            color = 'orange'
            text = 'Поточне'
        return format_html('<b style="color:{};">{}</b>', color, text)
    status_colored.short_description = 'Статус бронювання'


@admin.register(CallbackRequest)
class CallbackRequestAdmin(admin.ModelAdmin):
    list_display = ('name', 'phone', 'created_at', 'is_processed')
    list_filter = ('is_processed', 'created_at')
    search_fields = ('name', 'phone')
    list_editable = ('is_processed',)