'use client';

import React, { createContext, useContext, useState, useEffect } from 'react';
import {
  PERSONAS,
  Persona,
  MenuItem,
  Restaurant,
  RESTAURANTS_DATA,
  AIPlanOption,
  DEFAULT_AI_PLANS,
  PastOrder,
  MOCK_ORDERS_HISTORY,
  HYDERABAD_AREAS,
} from '@/data/mockData';

export interface CartItem {
  restaurantId: string;
  restaurantName: string;
  deliveryFee: number;
  item: MenuItem;
  quantity: number;
}

export interface ChatMessage {
  id: string;
  sender: 'user' | 'assistant';
  timestamp: string;
  text: string;
  thinkingSteps?: string[];
  plans?: AIPlanOption[];
  confirmation?: {
    id: string;
    title: string;
    restaurantName: string;
    restaurantId: string;
    itemsSummary: string;
    totalAmount: number;
    itemsToCart: CartItem[];
  };
}

interface DawatContextType {
  // User Persona
  activePersona: Persona;
  switchPersona: (id: 'priya' | 'arjun') => void;
  // Area Picker
  selectedArea: string;
  setSelectedArea: (area: string) => void;
  // Cart
  cart: CartItem[];
  addToCart: (restaurant: Pick<Restaurant, 'id' | 'name' | 'deliveryFee'>, item: MenuItem) => void;
  removeFromCart: (itemId: string) => void;
  updateQuantity: (itemId: string, delta: number) => void;
  clearCart: () => void;
  cartRestaurantId: string | null;
  cartRestaurantName: string | null;
  cartDeliveryFee: number;
  cartSubtotal: number;
  cartGst: number;
  cartGrandTotal: number;
  totalCartItemCount: number;
  // AI Chat
  isChatOpen: boolean;
  setIsChatOpen: (open: boolean) => void;
  openChatWithPrompt: (promptText: string) => void;
  chatMessages: ChatMessage[];
  sendChatMessage: (text: string) => void;
  handleSelectPlan: (plan: AIPlanOption) => void;
  handleConfirmOrder: (confId: string) => void;
  handleRejectOrder: (confId: string) => void;
  // Active Orders for tracking
  activeOrder: PastOrder | null;
  placeOrderFromCart: () => string; // returns orderId
}

const DawatContext = createContext<DawatContextType | undefined>(undefined);

export function DawatProvider({ children }: { children: React.ReactNode }) {
  const [activePersona, setActivePersona] = useState<Persona>(PERSONAS.arjun);
  const [selectedArea, setSelectedArea] = useState<string>('Banjara Hills');
  const [cart, setCart] = useState<CartItem[]>([
    {
      restaurantId: 'nawabs-dastarkhwan',
      restaurantName: "Nawab's Dastarkhwan",
      deliveryFee: 25,
      item: RESTAURANTS_DATA[0].menu[0], // Mutton Dum Biryani
      quantity: 1,
    },
    {
      restaurantId: 'nawabs-dastarkhwan',
      restaurantName: "Nawab's Dastarkhwan",
      deliveryFee: 25,
      item: RESTAURANTS_DATA[0].menu[5], // Mirchi Ka Salan
      quantity: 1,
    },
  ]);

  const [activeOrder, setActiveOrder] = useState<PastOrder | null>({
    orderId: 'DWT-90214',
    restaurantId: 'nawabs-dastarkhwan',
    restaurantName: "Nawab's Dastarkhwan",
    date: 'Just now',
    items: [
      { name: 'Mutton Dum Biryani (Kacchi Gosht)', quantity: 1, price: 440 },
      { name: 'Mirchi Ka Salan (Classic)', quantity: 1, price: 180 },
    ],
    itemTotal: 620,
    deliveryFee: 25,
    gst: 31,
    grandTotal: 676,
    status: 'Preparing',
    deliveryAddress: 'Villa 18, Gulmohar Enclave, Road 45, Jubilee Hills',
  });

  const [isChatOpen, setIsChatOpen] = useState(false);
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([
    {
      id: 'm-1',
      sender: 'assistant',
      timestamp: '10:30 AM',
      text: "Adaab! I am Dawat AI, your Nizami dining concierge. Tell me your craving, party size, or spice preference, and I'll curate the finest feast in Hyderabad.",
      thinkingSteps: [
        'Initialized Nizami taste profile engine',
        'Calibrated for Hyderabad localities & authentic dum kitchens',
        'Respecting active user profile & dietary criteria',
      ],
      plans: DEFAULT_AI_PLANS,
    },
  ]);

  const switchPersona = (id: 'priya' | 'arjun') => {
    setActivePersona(PERSONAS[id]);
  };

  // Cart operations
  const addToCart = (
    restaurant: Pick<Restaurant, 'id' | 'name' | 'deliveryFee'>,
    item: MenuItem
  ) => {
    setCart((prev) => {
      // Rule: One bill per restaurant. If cart has items from different restaurant, confirm switch or replace
      if (prev.length > 0 && prev[0].restaurantId !== restaurant.id) {
        // Reset cart to new restaurant
        return [
          {
            restaurantId: restaurant.id,
            restaurantName: restaurant.name,
            deliveryFee: restaurant.deliveryFee,
            item,
            quantity: 1,
          },
        ];
      }

      const existingIndex = prev.findIndex((ci) => ci.item.id === item.id);
      if (existingIndex > -1) {
        const updated = [...prev];
        updated[existingIndex].quantity += 1;
        return updated;
      }
      return [
        ...prev,
        {
          restaurantId: restaurant.id,
          restaurantName: restaurant.name,
          deliveryFee: restaurant.deliveryFee,
          item,
          quantity: 1,
        },
      ];
    });
  };

  const removeFromCart = (itemId: string) => {
    setCart((prev) => prev.filter((ci) => ci.item.id !== itemId));
  };

  const updateQuantity = (itemId: string, delta: number) => {
    setCart((prev) => {
      return prev
        .map((ci) => {
          if (ci.item.id === itemId) {
            const newQty = ci.quantity + delta;
            return newQty > 0 ? { ...ci, quantity: newQty } : null;
          }
          return ci;
        })
        .filter(Boolean) as CartItem[];
    });
  };

  const clearCart = () => {
    setCart([]);
  };

  const cartRestaurantId = cart.length > 0 ? cart[0].restaurantId : null;
  const cartRestaurantName = cart.length > 0 ? cart[0].restaurantName : null;
  const cartDeliveryFee = cart.length > 0 ? cart[0].deliveryFee : 0;
  const cartSubtotal = cart.reduce((sum, ci) => sum + ci.item.price * ci.quantity, 0);
  const cartGst = Math.round(cartSubtotal * 0.05 * 100) / 100;
  const cartGrandTotal = cartSubtotal > 0 ? Math.round(cartSubtotal + cartDeliveryFee + cartGst) : 0;
  const totalCartItemCount = cart.reduce((sum, ci) => sum + ci.quantity, 0);

  // Chat actions
  const openChatWithPrompt = (promptText: string) => {
    setIsChatOpen(true);
    sendChatMessage(promptText);
  };

  const sendChatMessage = (text: string) => {
    const userMsg: ChatMessage = {
      id: `usr-${Date.now()}`,
      sender: 'user',
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      text,
    };

    setChatMessages((prev) => [...prev, userMsg]);

    // Simulated intelligent response tailored to Hyderabad food
    setTimeout(() => {
      const lower = text.toLowerCase();
      let thinking: string[] = [
        `Analyzing query: "${text}"`,
        `Checking locality: ${selectedArea}`,
        `Matching persona filter: ${activePersona.name} (${activePersona.dietaryPreference})`,
        'Selecting authentic dum preparation & verifying spice balance',
      ];

      let replyText = '';
      let plans: AIPlanOption[] | undefined;
      let confirmation: ChatMessage['confirmation'];

      if (lower.includes('veg') || activePersona.dietaryPreference === 'Vegetarian') {
        replyText =
          "I have tailored a pure vegetarian royal feast from Anarkali Pure Veg & Thali in Jubilee Hills. Tarkari Dum Biryani infused with whole cardamom and pure saffron, paired with velvety Bagara Baingan and fresh Qubani sweet.";
        thinking.push('Applied strict 100% vegetarian filter');
        thinking.push('Verified no cross-kitchen oil usage');
        plans = DEFAULT_AI_PLANS.filter((p) => p.badge === 'Variety' || p.badge === 'Best value');
      } else if (lower.includes('spicy') || lower.includes('mutton') || lower.includes('hot')) {
        replyText =
          "For serious spice lovers, nothing rivals the charcoal-simmered Kacchi Gosht Biryani from Nawab's Dastarkhwan, served with piping hot Mirchi Ka Salan and crispy Tala Hua Gosht.";
        thinking.push('Identified preference for authentic Deccani heat');
        thinking.push('Matched acacia charcoal woodsmoke profile');
        plans = DEFAULT_AI_PLANS.filter((p) => p.badge === 'Best match' || p.badge === 'Best value');
      } else if (lower.includes('budget') || lower.includes('under') || lower.includes('value')) {
        replyText =
          "Here is the Best Value Nizami combo: Chicken Dum Biryani, Salan and Saffron Sheermal feeds two generously for under ₹700.";
        thinking.push('Calculated cost-per-serving optimization');
        plans = DEFAULT_AI_PLANS;
      } else {
        replyText =
          "I have evaluated 3 tailored plans for you across Banjara Hills and Jubilee Hills. Choose your ideal style below or request custom tweaks:";
        plans = DEFAULT_AI_PLANS;
      }

      const botMsg: ChatMessage = {
        id: `ast-${Date.now()}`,
        sender: 'assistant',
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        text: replyText,
        thinkingSteps: thinking,
        plans,
      };

      setChatMessages((prev) => [...prev, botMsg]);
    }, 600);
  };

  const handleSelectPlan = (plan: AIPlanOption) => {
    // Generate confirmation prompt
    const confMsg: ChatMessage = {
      id: `conf-${Date.now()}`,
      sender: 'assistant',
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      text: `Ready to order "${plan.title}" from ${plan.restaurantName}?`,
      confirmation: {
        id: `cf-${plan.id}`,
        title: plan.title,
        restaurantName: plan.restaurantName,
        restaurantId: plan.restaurantId,
        itemsSummary: plan.items.map((i) => `${i.quantity}x ${i.name}`).join(', '),
        totalAmount: plan.totalPrice,
        itemsToCart: plan.items.map((it) => ({
          restaurantId: plan.restaurantId,
          restaurantName: plan.restaurantName,
          deliveryFee: plan.deliveryFee,
          item: {
            id: it.id,
            name: it.name,
            description: `${it.name} from curated plan`,
            price: it.price,
            isVeg: it.isVeg,
            spiceLevel: it.spiceLevel as any,
            category: 'Curated Plan',
            illustrationType: (it.name.toLowerCase().includes('biryani') ? 'biryani' : 'curry') as any,
          },
          quantity: it.quantity,
        })),
      },
    };
    setChatMessages((prev) => [...prev, confMsg]);
  };

  const handleConfirmOrder = (confId: string) => {
    const msg = chatMessages.find((m) => m.confirmation?.id === confId);
    if (msg && msg.confirmation) {
      setCart(msg.confirmation.itemsToCart);
      const ackMsg: ChatMessage = {
        id: `ack-${Date.now()}`,
        sender: 'assistant',
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        text: `Splendid! All items from "${msg.confirmation.title}" have been placed in your Cart. You can review the single restaurant bill and place your order anytime!`,
      };
      setChatMessages((prev) => [...prev, ackMsg]);
    }
  };

  const handleRejectOrder = (confId: string) => {
    const rejectMsg: ChatMessage = {
      id: `rej-${Date.now()}`,
      sender: 'assistant',
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      text: "No problem at all. What would you like to adjust? (e.g. less spicy, pure veg, different budget, or a specific delicacy like Haleem or Irani Chai)?",
    };
    setChatMessages((prev) => [...prev, rejectMsg]);
  };

  const placeOrderFromCart = (): string => {
    const newOrderId = `DWT-${Math.floor(10000 + Math.random() * 90000)}`;
    const newOrder: PastOrder = {
      orderId: newOrderId,
      restaurantId: cartRestaurantId || 'nawabs-dastarkhwan',
      restaurantName: cartRestaurantName || "Nawab's Dastarkhwan",
      date: 'Just now',
      items: cart.map((ci) => ({
        name: ci.item.name,
        quantity: ci.quantity,
        price: ci.item.price,
      })),
      itemTotal: cartSubtotal,
      deliveryFee: cartDeliveryFee,
      gst: cartGst,
      grandTotal: cartGrandTotal,
      status: 'Preparing',
      deliveryAddress: activePersona.defaultAddress.line1 + ', ' + activePersona.defaultAddress.area,
    };
    setActiveOrder(newOrder);
    setCart([]);
    return newOrderId;
  };

  return (
    <DawatContext.Provider
      value={{
        activePersona,
        switchPersona,
        selectedArea,
        setSelectedArea,
        cart,
        addToCart,
        removeFromCart,
        updateQuantity,
        clearCart,
        cartRestaurantId,
        cartRestaurantName,
        cartDeliveryFee,
        cartSubtotal,
        cartGst,
        cartGrandTotal,
        totalCartItemCount,
        isChatOpen,
        setIsChatOpen,
        openChatWithPrompt,
        chatMessages,
        sendChatMessage,
        handleSelectPlan,
        handleConfirmOrder,
        handleRejectOrder,
        activeOrder,
        placeOrderFromCart,
      }}
    >
      {children}
    </DawatContext.Provider>
  );
}

export function useDawat() {
  const context = useContext(DawatContext);
  if (!context) {
    throw new Error('useDawat must be used within a DawatProvider');
  }
  return context;
}
