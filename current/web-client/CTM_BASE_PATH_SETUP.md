# Настройка базового пути /ctm для Web-клиента

## Обзор изменений

Web-клиент теперь работает по базовому пути `/ctm` вместо корневого `/`.

## Изменения в коде

### 1. Vite конфигурация (vite.config.ts)
```typescript
export default defineConfig({
  base: '/ctm/',  // Добавлен базовый путь
  // ...
})
```

### 2. Vue Router (src/router/index.ts)
```typescript
const router = createRouter({
  history: createWebHistory('/ctm/'),  // Изменен базовый путь
  // ...
})
```

## Сборка приложения

```bash
cd web-client
npm run build
```

Результат сборки будет в `web-client/dist/` с правильными путями для `/ctm`.

## Настройка веб-сервера

### Nginx

1. Скопируйте конфигурацию:
```bash
sudo cp deploy-to-prod/nginx-ctm.conf /etc/nginx/sites-available/construction-app
sudo ln -s /etc/nginx/sites-available/construction-app /etc/nginx/sites-enabled/
```

2. Скопируйте собранные файлы:
```bash
sudo mkdir -p /var/www/construction-app
sudo cp -r web-client/dist/* /var/www/construction-app/
```

3. Проверьте и перезагрузите nginx:
```bash
sudo nginx -t
sudo systemctl reload nginx
```

### Apache

Для Apache добавьте в конфигурацию:

```apache
<VirtualHost *:80>
    ServerName servut.npksarmat.ru
    DocumentRoot /var/www/construction-app

    # API proxy
    ProxyPass /api http://localhost:8000/api
    ProxyPassReverse /api http://localhost:8000/api

    # Web client at /ctm
    Alias /ctm /var/www/construction-app
    <Directory /var/www/construction-app>
        Options -Indexes +FollowSymLinks
        AllowOverride All
        Require all granted
        
        # SPA routing
        RewriteEngine On
        RewriteBase /ctm/
        RewriteRule ^index\.html$ - [L]
        RewriteCond %{REQUEST_FILENAME} !-f
        RewriteCond %{REQUEST_FILENAME} !-d
        RewriteRule . /ctm/index.html [L]
    </Directory>

    # Redirect root to /ctm
    RedirectMatch 301 ^/$ /ctm/
</VirtualHost>
```

### IIS (Windows Server)

1. Установите URL Rewrite Module
2. Создайте web.config в корне сайта:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<configuration>
    <system.webServer>
        <rewrite>
            <rules>
                <!-- Redirect root to /ctm -->
                <rule name="Redirect to CTM" stopProcessing="true">
                    <match url="^$" />
                    <action type="Redirect" url="/ctm/" redirectType="Permanent" />
                </rule>
                
                <!-- SPA routing for /ctm -->
                <rule name="CTM SPA" stopProcessing="true">
                    <match url="^ctm/.*" />
                    <conditions logicalGrouping="MatchAll">
                        <add input="{REQUEST_FILENAME}" matchType="IsFile" negate="true" />
                        <add input="{REQUEST_FILENAME}" matchType="IsDirectory" negate="true" />
                    </conditions>
                    <action type="Rewrite" url="/ctm/index.html" />
                </rule>
            </rules>
        </rewrite>
        
        <!-- API proxy -->
        <proxy>
            <rule name="API Proxy" stopProcessing="true">
                <match url="^api/(.*)" />
                <action type="Rewrite" url="http://localhost:8000/api/{R:1}" />
            </rule>
        </proxy>
    </system.webServer>
</configuration>
```

## Доступ к приложению

После настройки приложение будет доступно по адресу:
- **Web-клиент**: http://servut.npksarmat.ru/ctm/
- **API**: http://servut.npksarmat.ru/api/

## Разработка

Для локальной разработки используйте:

```bash
cd web-client
npm run dev
```

Dev-сервер будет работать на http://localhost:5173/ctm/

## Проверка

1. Откройте браузер и перейдите на http://servut.npksarmat.ru/ctm/
2. Проверьте, что все ресурсы загружаются корректно (откройте DevTools → Network)
3. Проверьте, что роутинг работает (переходы между страницами)
4. Проверьте, что API запросы работают

## Откат изменений

Если нужно вернуться к корневому пути `/`:

1. В `vite.config.ts` удалите `base: '/ctm/'`
2. В `src/router/index.ts` измените на `createWebHistory(import.meta.env.BASE_URL)`
3. Пересоберите приложение
4. Обновите конфигурацию веб-сервера
