from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.decorators import login_required
from .models import Portfolio
from django.contrib import messages
import yfinance as yf
import requests
from bs4 import BeautifulSoup
from django.http import JsonResponse
import ssl
import csv
import os
import json
import certifi
import urllib3
from decimal import Decimal
from django.views.decorators.http import require_POST
from django.core.cache import cache
from datetime import datetime, timedelta

# SSL uyarılarını ve doğrulamasını tamamen devre dışı bırak
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
ssl._create_default_https_context = ssl._create_unverified_context

# Önbellek süresi (saniye)
CACHE_TIMEOUT = 300  # 5 dakika

def home(request):
    return render(request, 'portfolio/home.html')

def register(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('home')
    else:
        form = UserCreationForm()
    return render(request, 'portfolio/register.html', {'form': form})

def login_view(request):
    if request.method == 'POST':
        form = AuthenticationForm(data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            if Portfolio.objects.filter(user=user).exists():
                return redirect('portfolio_list')
            return redirect('home')
    else:
        form = AuthenticationForm()
    return render(request, 'portfolio/login.html', {'form': form})

def logout_view(request):
    logout(request)
    return redirect('home')

def get_bist_stocks():
    try:
        # bistCompanies.json dosyasını oku
        with open('static/bistCompanies.json', 'r', encoding='utf-8') as file:
            companies = json.load(file)
            # Her şirket için (kod, "kod - isim") formatında tuple oluştur
            stocks = [(company['stock_code'], f"{company['stock_code']} - {company['stock_name']}") for company in companies]
            return sorted(stocks, key=lambda x: x[0])
    except Exception as e:
        print(f"bistCompanies.json okuma hatası: {e}")
        # Hata durumunda varsayılan listeyi döndür
        return [
            ('THYAO', 'THYAO - Türk Hava Yolları'),
            ('GARAN', 'GARAN - Garanti Bankası'),
            ('AKBNK', 'AKBNK - Akbank'),
            ('EREGL', 'EREGL - Ereğli Demir Çelik'),
            ('ASELS', 'ASELS - Aselsan'),
            ('KCHOL', 'KCHOL - Koç Holding'),
            ('SISE', 'SISE - Şişe Cam'),
            ('TUPRS', 'TUPRS - Tüpraş'),
            ('YKBNK', 'YKBNK - Yapı Kredi Bankası'),
            ('PETKM', 'PETKM - Petkim'),
            ('SAHOL', 'SAHOL - Sabancı Holding'),
            ('BIMAS', 'BIMAS - BİM Mağazalar'),
            ('TAVHL', 'TAVHL - TAV Havalimanları'),
            ('PGSUS', 'PGSUS - Pegasus'),
            ('ARCLK', 'ARCLK - Arçelik'),
            ('FROTO', 'FROTO - Ford Otosan'),
            ('TOASO', 'TOASO - Tofaş Türk Otomobil'),
            ('VESTL', 'VESTL - Vestel'),
            ('HEKTS', 'HEKTS - Hektaş'),
            ('SASA', 'SASA - SASA Polyester'),
        ]

def get_stock_price_from_isyatirim(stock_code):
    try:
        url = f"https://www.isyatirim.com.tr/tr-tr/analiz/hisse/Sayfalar/default.aspx?hisse={stock_code}"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Fiyat bilgisini bul
        price_element = soup.find('span', {'class': 'h3'})
        if price_element:
            price = float(price_element.text.strip().replace(',', '.'))
            return price, None, None
    except Exception as e:
        print(f"İş Yatırım'dan veri çekme hatası: {e}")
    return None, None, None

def get_stock_price_from_google(stock_code):
    try:
        url = f"https://www.google.com/finance/quote/{stock_code}:IST"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Fiyat bilgisini bul
        price_element = soup.find('div', {'class': 'YMlKec fxKbKc'})
        if price_element:
            # TL sembolünü ve noktalama işaretlerini temizle
            price_text = price_element.text.strip()
            price_text = price_text.replace('₺', '').replace(',', '')
            price = float(price_text)
            
            # Önceki kapanış fiyatını bul
            prev_close_element = soup.find('div', {'class': 'P6K39c'})
            prev_close = None
            if prev_close_element:
                prev_close_text = prev_close_element.text.strip()
                prev_close_text = prev_close_text.replace('₺', '').replace(',', '')
                prev_close = float(prev_close_text)
            
            # Yüzde değişimi bul
            percent_element = soup.find('div', {'class': 'JwB6zf'})
            percent = None
            if percent_element:
                percent_text = percent_element.text.strip().replace(',', '.').replace('%', '')
                percent = float(percent_text)
            
            return price, prev_close, percent
    except Exception as e:
        print(f"Google Finance'den veri çekme hatası: {e}")
    return None, None, None

def get_stock_price(stock_code):
    # Önbellekten kontrol et
    cache_key = f'stock_price_{stock_code}'
    cached_data = cache.get(cache_key)
    if cached_data:
        return cached_data

    try:
        # Önce Google Finance'dan dene
        price, previous_close, api_percent = get_stock_price_from_google(stock_code)
        if price and price > 0:
            result = (price, previous_close, api_percent)
            cache.set(cache_key, result, CACHE_TIMEOUT)
            return result
        # Google başarısız olursa Yahoo Finance'ı dene
        stock = yf.Ticker(stock_code + ".IS")
        price = stock.info.get('regularMarketPrice', 0)
        previous_close = stock.info.get('previousClose', 0)
        api_percent = stock.info.get('regularMarketChangePercent', None)
        if price and price > 0:
            if api_percent is not None:
                api_percent = api_percent * 100
            result = (price, previous_close, api_percent)
            cache.set(cache_key, result, CACHE_TIMEOUT)
            return result
        # Her iki kaynak da başarısız olursa None döndür
        return None, None, None
    except Exception as e:
        print(f"Fiyat alma hatası ({stock_code}): {e}")
        return None, None, None

@login_required
def portfolio_list(request):
    portfolios = Portfolio.objects.filter(user=request.user)
    portfolio_details = []
    total_profit_loss = 0
    total_daily_profit_loss = 0
    total_volume = 0
    for portfolio in portfolios:
        try:
            current_price, previous_close, api_percent = get_stock_price(portfolio.stock_code)
            if current_price is not None:
                profit_loss = (current_price - float(portfolio.buy_price)) * portfolio.quantity
                daily_diff = current_price - previous_close if previous_close else 0
                daily_profit_loss = daily_diff * portfolio.quantity
                daily_percent = api_percent if api_percent is not None else ((current_price - previous_close) / previous_close * 100) if previous_close else 0
                portfolio_details.append({
                    'portfolio': portfolio,
                    'current_price': current_price,
                    'profit_loss': profit_loss,
                    'daily_diff': daily_diff,
                    'daily_profit_loss': daily_profit_loss,
                    'daily_percent': daily_percent
                })
                total_profit_loss += profit_loss
                total_daily_profit_loss += daily_profit_loss
                total_volume += current_price * portfolio.quantity
            else:
                portfolio_details.append({
                    'portfolio': portfolio,
                    'current_price': 'Veri yok',
                    'profit_loss': 'N/A',
                    'daily_diff': 'N/A',
                    'daily_profit_loss': 'N/A',
                    'daily_percent': 'N/A'
                })
        except Exception as e:
            print(f"Portfolio işleme hatası ({portfolio.stock_code}): {str(e)}")
            portfolio_details.append({
                'portfolio': portfolio,
                'current_price': 'Hata',
                'profit_loss': 'N/A',
                'daily_diff': 'N/A',
                'daily_profit_loss': 'N/A',
                'daily_percent': 'N/A'
            })
    return render(request, 'portfolio/portfolio_list.html', {
        'portfolio_details': portfolio_details,
        'total_profit_loss': total_profit_loss,
        'total_daily_profit_loss': total_daily_profit_loss,
        'total_volume': total_volume,
        'stocks': get_bist_stocks(),
    })

@login_required
def portfolio_add(request):
    if request.method == 'POST':
        stock_code = request.POST.get('stock_code')
        buy_price = Decimal(request.POST.get('buy_price'))
        quantity = int(request.POST.get('quantity'))
        buy_date = request.POST.get('buy_date')
        try:
            existing = Portfolio.objects.filter(user=request.user, stock_code=stock_code).first()
            if existing:
                total_quantity = existing.quantity + quantity
                total_cost = (existing.buy_price * existing.quantity) + (buy_price * quantity)
                new_avg_price = total_cost / Decimal(total_quantity)
                existing.quantity = total_quantity
                existing.buy_price = new_avg_price.quantize(Decimal('0.01'))
                existing.buy_date = buy_date
                existing.save()
                messages.success(request, 'Mevcut hisse ile birleştirildi ve ortalama maliyet güncellendi!')
            else:
                Portfolio.objects.create(
                    user=request.user,
                    stock_code=stock_code,
                    buy_price=buy_price,
                    quantity=quantity,
                    buy_date=buy_date
                )
                messages.success(request, 'Hisse başarıyla eklendi!')
            return redirect('portfolio_list')
        except Exception as e:
            print('Hisse eklenirken hata:', e)
            messages.error(request, 'Hisse eklenirken bir hata oluştu!')
    stocks = get_bist_stocks()
    return render(request, 'portfolio/portfolio_add.html', {'stocks': stocks})

@login_required
def portfolio_edit(request, portfolio_id):
    portfolio = get_object_or_404(Portfolio, id=portfolio_id, user=request.user)
    if request.method == 'POST':
        try:
            portfolio.stock_code = request.POST.get('stock_code')
            portfolio.buy_price = request.POST.get('buy_price')
            portfolio.quantity = request.POST.get('quantity')
            portfolio.buy_date = request.POST.get('buy_date')
            portfolio.save()
            messages.success(request, 'Hisse başarıyla güncellendi!')
            return redirect('portfolio_list')
        except:
            messages.error(request, 'Hisse güncellenirken bir hata oluştu!')
    stocks = get_bist_stocks()
    return render(request, 'portfolio/portfolio_edit.html', {'portfolio': portfolio, 'stocks': stocks})

def get_current_price(request):
    stock_code = request.GET.get('stock_code')
    if stock_code:
        price, _, _ = get_stock_price(stock_code)
        if price:
            return JsonResponse({'price': price})
    return JsonResponse({'price': None})

@require_POST
@login_required
def add_quantity(request):
    portfolio_id = request.POST.get('portfolio_id')
    add_quantity = int(request.POST.get('quantity'))
    add_price = Decimal(request.POST.get('buy_price'))
    try:
        portfolio = Portfolio.objects.get(id=portfolio_id, user=request.user)
        total_quantity = portfolio.quantity + add_quantity
        total_cost = (portfolio.buy_price * portfolio.quantity) + (add_price * add_quantity)
        new_avg_price = total_cost / Decimal(total_quantity)
        portfolio.quantity = total_quantity
        portfolio.buy_price = new_avg_price.quantize(Decimal('0.01'))
        portfolio.save()
        # Güncel fiyat ve kar/zarar hesapla
        current_price, previous_close, api_percent = get_stock_price(portfolio.stock_code)
        profit_loss = (current_price - float(portfolio.buy_price)) * portfolio.quantity if current_price is not None else None
        daily_diff = current_price - previous_close if (current_price is not None and previous_close) else None
        daily_profit_loss = daily_diff * portfolio.quantity if daily_diff is not None else None
        daily_percent = api_percent if api_percent is not None else ((current_price - previous_close) / previous_close * 100) if (current_price is not None and previous_close) else None
        return JsonResponse({
            'success': True,
            'quantity': portfolio.quantity,
            'buy_price': str(portfolio.buy_price),
            'profit_loss': profit_loss,
            'daily_profit_loss': daily_profit_loss,
            'daily_percent': daily_percent
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@require_POST
@login_required
def remove_quantity(request):
    portfolio_id = request.POST.get('portfolio_id')
    remove_quantity = int(request.POST.get('quantity'))
    try:
        portfolio = Portfolio.objects.get(id=portfolio_id, user=request.user)
        new_quantity = portfolio.quantity - remove_quantity
        if new_quantity <= 0:
            portfolio.delete()
            return JsonResponse({'success': True, 'removed': True})
        else:
            portfolio.quantity = new_quantity
            portfolio.save()
            # Güncel fiyat ve kar/zarar hesapla
            current_price, previous_close, api_percent = get_stock_price(portfolio.stock_code)
            profit_loss = (current_price - float(portfolio.buy_price)) * portfolio.quantity if current_price is not None else None
            daily_diff = current_price - previous_close if (current_price is not None and previous_close) else None
            daily_profit_loss = daily_diff * portfolio.quantity if daily_diff is not None else None
            daily_percent = api_percent if api_percent is not None else ((current_price - previous_close) / previous_close * 100) if (current_price is not None and previous_close) else None
            return JsonResponse({
                'success': True,
                'quantity': portfolio.quantity,
                'profit_loss': profit_loss,
                'daily_profit_loss': daily_profit_loss,
                'daily_percent': daily_percent
            })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})
