# Web Client - Construction Time Management System

Vue.js 3 web client for the construction time management system.

## Tech Stack

- **Vue.js 3** - Progressive JavaScript framework
- **TypeScript** - Type-safe development
- **Vite** - Fast build tool and dev server
- **Vue Router** - Client-side routing
- **Pinia** - State management
- **CSS** - Project styles in `src/styles.css` and scoped component styles
- **Fetch wrapper** - API client in `src/api/client.ts`

## Project Structure

```
src/
├── api/          # API client layer (axios instances, API calls)
├── assets/       # Static assets (CSS, images)
├── components/   # Reusable Vue components
├── composables/  # Composition API functions
├── router/       # Vue Router configuration
├── stores/       # Pinia state management stores
├── types/        # TypeScript type definitions
├── views/        # Page-level components
├── App.vue       # Root component
└── main.ts       # Application entry point
```

## Development

### Prerequisites

- Node.js 18+ and npm

### Setup

```bash
# Install dependencies
npm install

# Start development server (runs on http://localhost:5173)
npm run dev

# Build for production
npm run build

# Preview production build
npm run preview

# Run E2E tests
npm run test:e2e
```

Unit-test, lint, and formatter scripts are not currently configured. They are
tracked as quality gaps in the repository-level `SPEC_REVIEW.md`.

## API Configuration

The development server is configured to proxy API requests to the backend:

- `/api/*` → `http://localhost:8000/api/*`

This is configured in `vite.config.ts`.

## Responsive Design

The application uses Tailwind CSS with custom breakpoints:

- **Mobile**: < 768px
- **Tablet**: 768px - 1023px
- **Desktop**: ≥ 1024px

## Implemented core areas

- User authentication with JWT
- Reference data management (counterparties, objects, works, persons, organizations)
- Estimate document management
- Daily report management
- Document posting workflow
- Print forms generation (PDF, Excel)
- Work execution register
- Responsive document forms

## Related documentation

- [`SPEC_REVIEW.md`](../../SPEC_REVIEW.md)
- [`DEVELOPMENT_PLAN.md`](../../DEVELOPMENT_PLAN.md)
- [`DOCUMENT_LIST_SPEC.md`](../../DOCUMENT_LIST_SPEC.md)
