# Web Client - Construction Time Management System

Vue.js 3 web client for the construction time management system.

## Tech Stack

- **Vue.js 3** - Progressive JavaScript framework
- **TypeScript** - Type-safe development
- **Vite** - Fast build tool and dev server
- **Vue Router** - Client-side routing
- **Pinia** - State management
- **Tailwind CSS** - Utility-first CSS framework
- **Axios** - HTTP client for API calls
- **VueUse** - Collection of Vue composition utilities
- **ESLint & Prettier** - Code quality and formatting

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

# Run tests
npm run test:unit

# Run E2E tests
npm run test:e2e

# Lint and fix files
npm run lint
npm run format
```

## API Configuration

The development server is configured to proxy API requests to the backend:

- `/api/*` → `http://localhost:8000/api/*`

This is configured in `vite.config.ts`.

## Responsive Design

The application uses Tailwind CSS with custom breakpoints:

- **Mobile**: < 768px
- **Tablet**: 768px - 1023px
- **Desktop**: ≥ 1024px

## Features (Planned)

- User authentication with JWT
- Reference data management (counterparties, objects, works, persons, organizations)
- Estimate document management
- Daily report management
- Document posting workflow
- Print forms generation (PDF, Excel)
- Work execution register
- Mobile-optimized interface

## Related Documentation

- [Requirements](./../.kiro/specs/web-client-access/requirements.md)
- [Design Document](./../.kiro/specs/web-client-access/design.md)
- [Implementation Tasks](./../.kiro/specs/web-client-access/tasks.md)
