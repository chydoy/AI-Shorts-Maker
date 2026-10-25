# Frontend: AI Shorts Maker

Next.js + Tailwind CSS интерфейс для AI Shorts Maker.

## Локальный запуск без Docker

```bash
npm install
npm run dev
```

Frontend будет доступен на http://localhost:3000.

По умолчанию API берётся из:

```text
http://localhost:8000
```

Для другого адреса задайте:

```bash
NEXT_PUBLIC_API_URL=http://localhost:8000
```

## Что реализовано

- валидация YouTube URL;
- `POST /api/v1/process`;
- polling `GET /api/v1/tasks/{id}` каждые 2 секунды;
- `GET /api/v1/tasks/{id}/fragments` после завершения;
- отображение статуса `pending → downloading → transcribing → analyzing → completed`;
- карточки фрагментов;
- таймкод и длительность;
- кнопка предпросмотра, открывающая исходное YouTube-видео на нужной секунде.
