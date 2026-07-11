import { computed } from 'vue'
import { useAuthStore } from '../stores/auth'

export function useSpecificationReview() {
  const auth = useAuthStore()

  const specificationReviewEnabled = computed(() => auth.user?.use_specification_review ?? false)

  return {
    specificationReviewEnabled,
  }
}
