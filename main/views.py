from django.shortcuts import render, get_object_or_404, redirect
from django.db.models import Q
from django.contrib import messages
from django.utils import timezone
from datetime import datetime, timedelta
from .models import Room, Booking, BookingRequest, CallbackRequest


def is_room_available(room_id, check_in, check_out):
    if not room_id or not check_in or not check_out:
        return False
    return not Booking.objects.filter(
        room_id=room_id,
        check_in__lt=check_out,
        check_out__gt=check_in
    ).exists()


def index(request):
    featured_rooms = Room.objects.filter(is_active=True)[:3]
    return render(request, 'index.html', {'rooms': featured_rooms})


def rooms(request):
    check_in = request.GET.get('check_in')
    check_out = request.GET.get('check_out')
    rooms_queryset = Room.objects.filter(is_active=True)

    if check_in and check_out:
        try:
            d1 = datetime.strptime(check_in, '%Y-%m-%d').date()
            d2 = datetime.strptime(check_out, '%Y-%m-%d').date()
            if d1 < d2:
                occupied_ids = Booking.objects.filter(
                    Q(check_in__lt=d2) & Q(check_out__gt=d1)
                ).values_list('room_id', flat=True)
                rooms_queryset = rooms_queryset.exclude(id__in=occupied_ids)
        except (ValueError, TypeError):
            pass

    return render(request, 'room.html', {'rooms': rooms_queryset})


def room_detail(request, slug):
    room = get_object_or_404(Room, slug=slug)
    return render(request, 'rooms/rooms_page.html', {'room': room})


def booking(request):
    selected_room_id = request.GET.get('room_id')
    check_in_val = request.GET.get('check_in')
    check_out_val = request.GET.get('check_out')

    available_rooms = Room.objects.filter(is_active=True)
    if check_in_val and check_out_val:
        try:
            d1 = datetime.strptime(check_in_val, '%Y-%m-%d').date()
            d2 = datetime.strptime(check_out_val, '%Y-%m-%d').date()
            if d1 < d2:
                occupied = Booking.objects.filter(
                    Q(check_in__lt=d2) & Q(check_out__gt=d1)
                ).values_list('room_id', flat=True)
                available_rooms = available_rooms.exclude(id__in=occupied)
        except (ValueError, TypeError):
            pass

    if request.method == 'POST':
        room_id = request.POST.get('room_id')
        first_name = request.POST.get('customer_first_name', '').strip()
        last_name = request.POST.get('customer_last_name', '').strip()
        phone = request.POST.get('customer_phone', '').strip()
        guests_count = int(request.POST.get('guests_count', 1))
        c_in_str = request.POST.get('check_in')
        c_out_str = request.POST.get('check_out')
        msg = request.POST.get('message', '')

        if not all([room_id, c_in_str, c_out_str, phone]):
            messages.error(request, "Помилка: Заповніть всі обов'язкові поля.")
            return redirect('booking')

        try:
            d1 = datetime.strptime(c_in_str, '%Y-%m-%d').date()
            d2 = datetime.strptime(c_out_str, '%Y-%m-%d').date()

            if d1 >= d2:
                messages.error(request, "Дата виїзду має бути пізніше дати заїзду.")
                return redirect('booking')

            if not is_room_available(room_id, d1, d2):
                messages.error(request, "На жаль, цей номер уже забронювали на вибрані дати.")
                return redirect('booking')

            full_name = f"{first_name} {last_name}".strip()

            time_threshold = timezone.now() - timedelta(minutes=30)
            if BookingRequest.objects.filter(
                customer_phone=phone, created_at__gte=time_threshold
            ).exists():
                messages.error(request, "Ви вже надсилали запит нещодавно. Будь ласка, зачекайте або зателефонуйте.")
                return redirect('booking')

            BookingRequest.objects.create(
                room_id=room_id,
                customer_name=full_name,
                customer_phone=phone,
                guests_count=guests_count,
                check_in=d1,
                check_out=d2,
                message=msg
            )

            messages.success(request, "✅ Ваш запит на бронювання успішно надіслано!")
            return redirect('index')

        except (ValueError, TypeError):
            messages.error(request, "Помилка у форматі дат.")
            return redirect('booking')

    return render(request, 'booking.html', {
        'available_rooms': available_rooms,
        'selected_room_id': selected_room_id,
        'check_in': check_in_val,
        'check_out': check_out_val,
    })


def facilities(request):
    return render(request, 'service.html')


def contact(request):
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        phone = request.POST.get('phone', '').strip().replace(" ", "")
        email = request.POST.get('email', '').strip()
        message = request.POST.get('message', '').strip()

        if not all([name, phone, email, message]):
            messages.error(request, "Будь ласка, заповніть всі обов'язкові поля (включаючи Email).")
            return redirect('contact')

        clean_phone = phone.replace("+", "")
        if not clean_phone.isdigit():
            messages.error(request, "Номер телефону має містити лише цифри.")
            return redirect('contact')

        if CallbackRequest.is_spam(name, phone):
            messages.error(request, "Ви вже надсилали запит нещодавно. Будь ласка, зачекайте 30 хвилин.")
            return redirect('contact')

        CallbackRequest.objects.create(
            name=name, phone=phone, email=email, message=message
        )
        messages.success(request, "Дякуємо! Ми зателефонуємо вам найближчим часом.")
        return redirect('contact')

    return render(request, 'contact.html')


def privacy_policy(request):
    return render(request, 'privacy_policy/privacy_policy.html')
