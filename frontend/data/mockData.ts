export interface MenuItem {
  id: string;
  name: string;
  description: string;
  price: number;
  isVeg: boolean;
  spiceLevel: 'Not spicy' | 'Mild' | 'Medium' | 'Hot';
  category: string;
  illustrationType: 'biryani' | 'haleem' | 'kebab' | 'curry' | 'bread' | 'chai' | 'sweet' | 'thali';
}

export interface Restaurant {
  id: string;
  name: string;
  tagline: string;
  locality: string;
  address: string;
  distanceKm: number;
  deliveryFee: number; // 0 means Free delivery
  priceLevel: '₹' | '₹₹' | '₹₹₹';
  cuisines: string[];
  isPureVeg: boolean;
  featuredChain?: string;
  heroBadge: string;
  menuCategories: string[];
  menu: MenuItem[];
}

export interface Persona {
  id: 'priya' | 'arjun' | 'guest';
  name: string;
  email: string;
  roleBadge: string;
  dietaryPreference: 'Vegetarian' | 'Non-Vegetarian' | 'Flexible';
  spiceTolerance: 'Not spicy' | 'Mild' | 'Medium' | 'Hot';
  defaultAddress: {
    label: string;
    line1: string;
    area: string;
    city: string;
    pincode: string;
  };
  savedAddresses: Array<{
    id: string;
    label: string;
    line1: string;
    area: string;
    city: string;
    pincode: string;
  }>;
  favoriteCuisines: string[];
}

export const HYDERABAD_AREAS = [
  'Banjara Hills',
  'Jubilee Hills',
  'Madhapur',
  'Charminar',
  'Gachibowli',
  'Begumpet',
  'Tolichowki',
  'Secunderabad',
  'Hitec City',
  'Mehdipatnam',
] as const;

export const CUISINES_LIST = [
  { id: 'biryani', name: 'Dum Biryani', iconName: 'biryani', count: 18 },
  { id: 'irani', name: 'Irani Chai & Osmania', iconName: 'chai', count: 12 },
  { id: 'kebab', name: 'Kebabs & Tandoor', iconName: 'kebab', count: 15 },
  { id: 'pure-veg', name: 'Pure Veg Nizami', iconName: 'thali', count: 9 },
  { id: 'haleem', name: 'Slow-Cooked Haleem', iconName: 'haleem', count: 8 },
  { id: 'curry', name: 'Shahi Curries & Salan', iconName: 'curry', count: 14 },
  { id: 'sweets', name: 'Meetha & Desserts', iconName: 'sweet', count: 11 },
] as const;

export const FAMOUS_CHAINS = [
  {
    name: 'Bawarchi Heritage Kitchen',
    highlight: 'Kacchi Gosht Dum Biryani & Tala Hua Gosht',
    branches: 'RTC X Roads, Banjara Hills & Madhapur',
    distanceKm: 1.6,
    deliveryFee: 25,
  },
  {
    name: 'Pista House Craft Kitchen',
    highlight: 'Royal Deccani Haleem & Irani Zafrani Chai',
    branches: 'Charminar, Gachibowli & Tolichowki',
    distanceKm: 2.4,
    deliveryFee: 0,
  },
  {
    name: 'Paradise Nizami Heritage',
    highlight: 'Classic Double Masala Dum Biryani & Mirchi Salan',
    branches: 'Secunderabad & Hitec City',
    distanceKm: 3.1,
    deliveryFee: 30,
  },
  {
    name: 'Grand Dawat Kitchens',
    highlight: 'Family Handi Feasts, Sheermal & Marag',
    branches: 'Jubilee Hills & Begumpet',
    distanceKm: 0.9,
    deliveryFee: 0,
  },
];

export const RESTAURANTS_DATA: Restaurant[] = [
  {
    id: 'nawabs-dastarkhwan',
    name: "Nawab's Dastarkhwan",
    tagline: 'Legacy Deccani dum cooking over slow acacia charcoal',
    locality: 'Banjara Hills',
    address: 'Road No. 10, Banjara Hills, Hyderabad',
    distanceKm: 1.4,
    deliveryFee: 25,
    priceLevel: '₹₹',
    cuisines: ['Dum Biryani', 'Kebabs & Tandoor', 'Nizami Mughlai'],
    isPureVeg: false,
    featuredChain: 'Grand Dawat Kitchens',
    heroBadge: 'Acacia Charcoal Specialist',
    menuCategories: ['Royal Biryani', 'Kebabs & Starters', 'Nizami Curries', 'Breads & Accompaniments', 'Shahi Meetha'],
    menu: [
      {
        id: 'nb-1',
        name: 'Mutton Dum Biryani (Kacchi Gosht)',
        description: 'Tender Telangana mutton marinated overnight in crushed green chillies, shahi jeera, saffron milk and slow-dum in sealed degh.',
        price: 440,
        isVeg: false,
        spiceLevel: 'Hot',
        category: 'Royal Biryani',
        illustrationType: 'biryani',
      },
      {
        id: 'nb-2',
        name: 'Nizami Chicken Dum Biryani',
        description: 'Long-grain aged basmati rice layered with succulent chicken cuts, caramelized onions (birista) and royal saffron pot essence.',
        price: 360,
        isVeg: false,
        spiceLevel: 'Medium',
        category: 'Royal Biryani',
        illustrationType: 'biryani',
      },
      {
        id: 'nb-3',
        name: 'Hyderabadi Tala Hua Gosht',
        description: 'Crispy fried spiced lamb morsels with crushed black pepper, fresh curry leaves and slivered garlic.',
        price: 380,
        isVeg: false,
        spiceLevel: 'Hot',
        category: 'Kebabs & Starters',
        illustrationType: 'kebab',
      },
      {
        id: 'nb-4',
        name: 'Charminar Shikampur Kebab',
        description: 'Melt-in-mouth ground meat patties stuffed with spiced hung curd, mint and chopped shallots.',
        price: 320,
        isVeg: false,
        spiceLevel: 'Medium',
        category: 'Kebabs & Starters',
        illustrationType: 'kebab',
      },
      {
        id: 'nb-5',
        name: 'Dum Ka Chicken (White Gravy)',
        description: 'Slow-simmered chicken in rich almond, poppy seed, melon seed paste and whole Nizami pot spices.',
        price: 340,
        isVeg: false,
        spiceLevel: 'Mild',
        category: 'Nizami Curries',
        illustrationType: 'curry',
      },
      {
        id: 'nb-6',
        name: 'Mirchi Ka Salan (Classic)',
        description: 'Thick nutty gravy made of roasted sesame, roasted peanuts, dry coconut, spiced Bhavnagri chillies and tamarind pulp.',
        price: 180,
        isVeg: true,
        spiceLevel: 'Hot',
        category: 'Nizami Curries',
        illustrationType: 'curry',
      },
      {
        id: 'nb-7',
        name: 'Saffron Sheermal & Roomali (Set of 2)',
        description: 'Warm saffron-infused flatbread brushed with pure ghee alongside ultra-thin hand-stretched roomali roti.',
        price: 110,
        isVeg: true,
        spiceLevel: 'Not spicy',
        category: 'Breads & Accompaniments',
        illustrationType: 'bread',
      },
      {
        id: 'nb-8',
        name: 'Shahi Double Ka Meetha',
        description: 'Fried bread crisps soaked in thickened saffron rabri, laced with cardamom and toasted almond slivers.',
        price: 150,
        isVeg: true,
        spiceLevel: 'Not spicy',
        category: 'Shahi Meetha',
        illustrationType: 'sweet',
      },
    ],
  },
  {
    id: 'anarkali-veg',
    name: 'Anarkali Pure Veg & Thali',
    tagline: 'Authentic 100% vegetarian Nizami and Deccani royal feast',
    locality: 'Jubilee Hills',
    address: 'Near Checkpost, Jubilee Hills, Hyderabad',
    distanceKm: 2.1,
    deliveryFee: 0,
    priceLevel: '₹₹',
    cuisines: ['Pure Veg Nizami', 'Shahi Curries & Salan', 'Meetha & Desserts'],
    isPureVeg: true,
    heroBadge: '100% Pure Vegetarian Kitchen',
    menuCategories: ['Royal Thalis', 'Tarkari & Biryani', 'Heritage Curries', 'Rotis', 'Desserts'],
    menu: [
      {
        id: 'av-1',
        name: 'Nizami Tarkari Dum Biryani',
        description: 'Flavoured basmati layered with baby carrots, beans, florets, paneer cubes, and golden mint infusion. Served with burani raita.',
        price: 310,
        isVeg: true,
        spiceLevel: 'Medium',
        category: 'Tarkari & Biryani',
        illustrationType: 'biryani',
      },
      {
        id: 'av-2',
        name: 'Deccani Royal Shahi Thali',
        description: 'Complete feast: Subz Biryani, Bagara Baingan, Paneer Korma, Khatti Dal, 2 Phulkas, Papad, Mirchi Salan, and Qubani Meetha.',
        price: 420,
        isVeg: true,
        spiceLevel: 'Mild',
        category: 'Royal Thalis',
        illustrationType: 'thali',
      },
      {
        id: 'av-3',
        name: 'Authentic Bagara Baingan',
        description: 'Tender baby brinjals slit and cooked in a velvety roasted sesame, peanut, tamarind and cumin masala gravy.',
        price: 240,
        isVeg: true,
        spiceLevel: 'Medium',
        category: 'Heritage Curries',
        illustrationType: 'curry',
      },
      {
        id: 'av-4',
        name: 'Hyderabadi Khatti Dal',
        description: 'Toor dal tempered with garlic, cumin, mustard seeds, curry leaves, green chillies and fresh tangy tamarind.',
        price: 190,
        isVeg: true,
        spiceLevel: 'Mild',
        category: 'Heritage Curries',
        illustrationType: 'curry',
      },
      {
        id: 'av-5',
        name: 'Paneer Chandni Tikka',
        description: 'Soft cottage cheese chunks marinated in cream, cashew paste, crushed white pepper and green cardamom.',
        price: 290,
        isVeg: true,
        spiceLevel: 'Not spicy',
        category: 'Tarkari & Biryani',
        illustrationType: 'kebab',
      },
      {
        id: 'av-6',
        name: 'Tawa Kulcha & Garlic Naan',
        description: 'Clay-oven fired bread with chopped garlic, butter and fresh coriander leaves.',
        price: 85,
        isVeg: true,
        spiceLevel: 'Not spicy',
        category: 'Rotis',
        illustrationType: 'bread',
      },
      {
        id: 'av-7',
        name: 'Qubani Ka Meetha with Fresh Malai',
        description: 'Stewed Turkish apricots with cracked apricot kernels served with cold whipped milk cream.',
        price: 160,
        isVeg: true,
        spiceLevel: 'Not spicy',
        category: 'Desserts',
        illustrationType: 'sweet',
      },
    ],
  },
  {
    id: 'al-qasba-irani',
    name: 'Al-Qasba Irani Cafe',
    tagline: 'Steaming samovars, Osmania biscuits and Old City teatime classics',
    locality: 'Charminar',
    address: 'Near Madina Circle, Old City, Charminar, Hyderabad',
    distanceKm: 3.8,
    deliveryFee: 30,
    priceLevel: '₹',
    cuisines: ['Irani Chai & Osmania', 'Kebabs & Starters'],
    isPureVeg: false,
    heroBadge: 'Traditional Brass Samovar Brew',
    menuCategories: ['Irani Samovar Chai', 'Teatime Snacks & Bakery', 'Old City Savouries'],
    menu: [
      {
        id: 'aq-1',
        name: 'Zafrani Irani Chai (Flask - Serves 3)',
        description: 'Slow-brewed strong Ceylon decoction blended with reduced thickened creamy milk, cardamom and Kashmiri saffron.',
        price: 120,
        isVeg: true,
        spiceLevel: 'Not spicy',
        category: 'Irani Samovar Chai',
        illustrationType: 'chai',
      },
      {
        id: 'aq-2',
        name: 'Classic Osmania Biscuits (Box of 8)',
        description: 'Sweet and mildly salted crumbly Nizam-era tea biscuits baked fresh daily in woodfired ovens.',
        price: 90,
        isVeg: true,
        spiceLevel: 'Not spicy',
        category: 'Teatime Snacks & Bakery',
        illustrationType: 'sweet',
      },
      {
        id: 'aq-3',
        name: 'Keema Lukhmi (Set of 2)',
        description: 'Crisp square pastry pockets stuffed with minced spiced mutton, onions and mint.',
        price: 130,
        isVeg: false,
        spiceLevel: 'Medium',
        category: 'Old City Savouries',
        illustrationType: 'kebab',
      },
      {
        id: 'aq-4',
        name: 'Vegetable Lukhmi (Set of 2)',
        description: 'Crisp pastry triangles stuffed with spiced potatoes, green peas and Deccani herbs.',
        price: 90,
        isVeg: true,
        spiceLevel: 'Mild',
        category: 'Old City Savouries',
        illustrationType: 'bread',
      },
      {
        id: 'aq-5',
        name: 'Bun Maska with Jam',
        description: 'Pillow-soft bakery bun generously slathered with salted churned butter and fruit compote.',
        price: 70,
        isVeg: true,
        spiceLevel: 'Not spicy',
        category: 'Teatime Snacks & Bakery',
        illustrationType: 'bread',
      },
    ],
  },
  {
    id: 'deccan-claypot',
    name: 'Deccan Claypot Co.',
    tagline: 'Sealed earthen handi biryanis with woodsmoke depth',
    locality: 'Madhapur',
    address: 'Near Ayyappa Society Main Rd, Madhapur, Hyderabad',
    distanceKm: 1.1,
    deliveryFee: 0,
    priceLevel: '₹₹',
    cuisines: ['Dum Biryani', 'Slow-Cooked Haleem', 'Shahi Curries & Salan'],
    isPureVeg: false,
    heroBadge: 'Unbroken Claypot Dum',
    menuCategories: ['Handi Biryani', 'Royal Haleem', 'Rich Gravies', 'Beverages'],
    menu: [
      {
        id: 'dc-1',
        name: 'Claypot Asli Mutton Biryani',
        description: 'Individual hand-thrown unglazed claypot, sealed with flour dough and cooked on charcoal embers for pure earthy scent.',
        price: 460,
        isVeg: false,
        spiceLevel: 'Hot',
        category: 'Handi Biryani',
        illustrationType: 'biryani',
      },
      {
        id: 'dc-2',
        name: 'Royal Shahi Mutton Haleem (Pure Ghee)',
        description: '12-hour pounded broken wheat, lentils and tender meat emulsified with pure desi ghee, cinnamon and fried onions.',
        price: 340,
        isVeg: false,
        spiceLevel: 'Medium',
        category: 'Royal Haleem',
        illustrationType: 'haleem',
      },
      {
        id: 'dc-3',
        name: 'Mutton Marag (Nizami Soup)',
        description: 'Clear aromatic broth cooked with bone-in mutton ribs, pistachios, almonds, black cardamom and peppercorn.',
        price: 270,
        isVeg: false,
        spiceLevel: 'Hot',
        category: 'Royal Haleem',
        illustrationType: 'curry',
      },
      {
        id: 'dc-4',
        name: 'Paneer Handi Biryani',
        description: 'Tender tandoori paneer and basmati rice infused with whole spices and saffron in individual clay pot.',
        price: 320,
        isVeg: true,
        spiceLevel: 'Medium',
        category: 'Handi Biryani',
        illustrationType: 'biryani',
      },
    ],
  },
  {
    id: 'golconda-spicery',
    name: 'Golconda Spicery',
    tagline: 'Bold, robust Telangana pepper-roasts and fiery Guntur marinades',
    locality: 'Gachibowli',
    address: 'Opposite Biodiversity Park, Gachibowli, Hyderabad',
    distanceKm: 4.2,
    deliveryFee: 35,
    priceLevel: '₹₹₹',
    cuisines: ['Kebabs & Tandoor', 'Dum Biryani', 'Shahi Curries & Salan'],
    isPureVeg: false,
    heroBadge: 'Spice Craft Excellence',
    menuCategories: ['Fiery Starters', 'Pulao & Biryani', 'Curries', 'Accompaniments'],
    menu: [
      {
        id: 'gs-1',
        name: 'Guntur Chilli Chicken Fry',
        description: 'Boneless chicken cubes tossed with fiery sun-dried red chillies, crushed garlic, and toasted coriander seeds.',
        price: 350,
        isVeg: false,
        spiceLevel: 'Hot',
        category: 'Fiery Starters',
        illustrationType: 'kebab',
      },
      {
        id: 'gs-2',
        name: 'Pathar Ka Gosht (Stone Grilled Lamb)',
        description: 'Thin mutton fillets marinated in raw papaya and Deccani pot spices, seared over heated natural river stone slab.',
        price: 430,
        isVeg: false,
        spiceLevel: 'Hot',
        category: 'Fiery Starters',
        illustrationType: 'kebab',
      },
      {
        id: 'gs-3',
        name: 'Banjara Spiced Chicken Biryani',
        description: 'Intensely fragrant basmati biryani with extra pepper heat and caramelized green chillies.',
        price: 380,
        isVeg: false,
        spiceLevel: 'Hot',
        category: 'Pulao & Biryani',
        illustrationType: 'biryani',
      },
      {
        id: 'gs-4',
        name: 'Dal Makhani & Roomali Combo',
        description: 'Velvety slow-simmered black lentils tempered with butter and cream to balance fiery starters.',
        price: 240,
        isVeg: true,
        spiceLevel: 'Not spicy',
        category: 'Curries',
        illustrationType: 'curry',
      },
    ],
  },
  {
    id: 'shahi-meetha',
    name: 'Shahi Dawaat Sweets & Chai',
    tagline: 'Royal Nizami confectionery, warm silver-leaf desserts and confectionery',
    locality: 'Tolichowki',
    address: 'Paramount Hills, Tolichowki, Hyderabad',
    distanceKm: 2.7,
    deliveryFee: 20,
    priceLevel: '₹₹',
    cuisines: ['Meetha & Desserts', 'Irani Chai & Osmania'],
    isPureVeg: true,
    heroBadge: 'Dessert Masters of the Deccan',
    menuCategories: ['Classic Meetha', 'Royal Halwas', 'Chai Flasks'],
    menu: [
      {
        id: 'sm-1',
        name: 'Gilded Double Ka Meetha (Half Kg)',
        description: 'Crisped bread immersed in saffron cardamom syrup, topped with thick clotted rabri and edible silver leaf (varq).',
        price: 260,
        isVeg: true,
        spiceLevel: 'Not spicy',
        category: 'Classic Meetha',
        illustrationType: 'sweet',
      },
      {
        id: 'sm-2',
        name: 'Qubani Malai Delight (Serves 2)',
        description: 'Sun-dried Hunza apricots slowly stewed with whole apricot almonds, layered with cold thickened cream.',
        price: 210,
        isVeg: true,
        spiceLevel: 'Not spicy',
        category: 'Classic Meetha',
        illustrationType: 'sweet',
      },
      {
        id: 'sm-3',
        name: 'Badam Ka Kund (Almond Sweetmeat)',
        description: 'Traditional baked almond paste fudge with ghee and saffron, served warm in earthenware cups.',
        price: 290,
        isVeg: true,
        spiceLevel: 'Not spicy',
        category: 'Royal Halwas',
        illustrationType: 'sweet',
      },
      {
        id: 'sm-4',
        name: 'Kulfi Falooda with Rose Sharbat',
        description: 'Rich creamy malai kulfi over cornstarch noodles, soaked sabja basil seeds and heritage damask rose drizzle.',
        price: 180,
        isVeg: true,
        spiceLevel: 'Not spicy',
        category: 'Classic Meetha',
        illustrationType: 'sweet',
      },
    ],
  },
];

export const PERSONAS: Record<'priya' | 'arjun', Persona> = {
  priya: {
    id: 'priya',
    name: 'Priya Sharma',
    email: 'priya.sharma@example.com',
    roleBadge: 'Vegetarian Gourmet',
    dietaryPreference: 'Vegetarian',
    spiceTolerance: 'Mild',
    defaultAddress: {
      label: 'Home',
      line1: 'Flat 402, Lotus Towers, Road 3',
      area: 'Madhapur',
      city: 'Hyderabad',
      pincode: '500081',
    },
    savedAddresses: [
      {
        id: 'addr-1',
        label: 'Home',
        line1: 'Flat 402, Lotus Towers, Road 3',
        area: 'Madhapur',
        city: 'Hyderabad',
        pincode: '500081',
      },
      {
        id: 'addr-2',
        label: 'Office',
        line1: 'Cyber Gateway, 5th Floor, Block B',
        area: 'Hitec City',
        city: 'Hyderabad',
        pincode: '500081',
      },
    ],
    favoriteCuisines: ['Pure Veg Nizami', 'Meetha & Desserts', 'Irani Chai & Osmania'],
  },
  arjun: {
    id: 'arjun',
    name: 'Arjun Reddy',
    email: 'arjun.reddy@example.com',
    roleBadge: 'Spicy Dum Biryani Enthusiast',
    dietaryPreference: 'Non-Vegetarian',
    spiceTolerance: 'Hot',
    defaultAddress: {
      label: 'Home',
      line1: 'Villa 18, Gulmohar Enclave, Road 45',
      area: 'Jubilee Hills',
      city: 'Hyderabad',
      pincode: '500033',
    },
    savedAddresses: [
      {
        id: 'addr-3',
        label: 'Home',
        line1: 'Villa 18, Gulmohar Enclave, Road 45',
        area: 'Jubilee Hills',
        city: 'Hyderabad',
        pincode: '500033',
      },
      {
        id: 'addr-4',
        label: 'Studio',
        line1: 'Studio 7, Film Nagar Main Road',
        area: 'Jubilee Hills',
        city: 'Hyderabad',
        pincode: '500096',
      },
    ],
    favoriteCuisines: ['Dum Biryani', 'Kebabs & Tandoor', 'Slow-Cooked Haleem'],
  },
};

export interface PastOrder {
  orderId: string;
  restaurantId: string;
  restaurantName: string;
  date: string;
  items: Array<{ name: string; quantity: number; price: number }>;
  itemTotal: number;
  deliveryFee: number;
  gst: number;
  grandTotal: number;
  status: 'Delivered' | 'In transit' | 'Preparing';
  deliveryAddress: string;
}

export const MOCK_ORDERS_HISTORY: PastOrder[] = [
  {
    orderId: 'DWT-88219',
    restaurantId: 'nawabs-dastarkhwan',
    restaurantName: "Nawab's Dastarkhwan",
    date: 'Yesterday, 8:40 PM',
    items: [
      { name: 'Mutton Dum Biryani (Kacchi Gosht)', quantity: 1, price: 440 },
      { name: 'Mirchi Ka Salan (Classic)', quantity: 1, price: 180 },
      { name: 'Shahi Double Ka Meetha', quantity: 1, price: 150 },
    ],
    itemTotal: 770,
    deliveryFee: 25,
    gst: 38.5,
    grandTotal: 833.5,
    status: 'Delivered',
    deliveryAddress: 'Road No. 10, Banjara Hills',
  },
  {
    orderId: 'DWT-76402',
    restaurantId: 'anarkali-veg',
    restaurantName: 'Anarkali Pure Veg & Thali',
    date: '05 Oct 2026, 1:15 PM',
    items: [
      { name: 'Deccani Royal Shahi Thali', quantity: 2, price: 840 },
      { name: 'Qubani Ka Meetha with Fresh Malai', quantity: 1, price: 160 },
    ],
    itemTotal: 1000,
    deliveryFee: 0,
    gst: 50,
    grandTotal: 1050,
    status: 'Delivered',
    deliveryAddress: 'Flat 402, Lotus Towers, Madhapur',
  },
];

export interface AIPlanOption {
  id: 'best-value' | 'best-match' | 'variety';
  badge: 'Best value' | 'Best match' | 'Variety';
  title: string;
  restaurantId: string;
  restaurantName: string;
  distanceKm: number;
  deliveryFee: number;
  totalPrice: number;
  servesCount: number;
  description: string;
  items: Array<{ id: string; name: string; quantity: number; price: number; isVeg: boolean; spiceLevel: string }>;
  tags: string[];
}

export const DEFAULT_AI_PLANS: AIPlanOption[] = [
  {
    id: 'best-value',
    badge: 'Best value',
    title: 'Nizami Family Combo',
    restaurantId: 'nawabs-dastarkhwan',
    restaurantName: "Nawab's Dastarkhwan",
    distanceKm: 1.4,
    deliveryFee: 25,
    totalPrice: 650,
    servesCount: 2,
    description: 'Generous portions designed for maximum value without compromising on dum cooked authenticity.',
    items: [
      { id: 'nb-2', name: 'Nizami Chicken Dum Biryani', quantity: 1, price: 360, isVeg: false, spiceLevel: 'Medium' },
      { id: 'nb-6', name: 'Mirchi Ka Salan (Classic)', quantity: 1, price: 180, isVeg: true, spiceLevel: 'Hot' },
      { id: 'nb-7', name: 'Saffron Sheermal & Roomali (Set of 2)', quantity: 1, price: 110, isVeg: true, spiceLevel: 'Not spicy' },
    ],
    tags: ['Under ₹700', 'Feeds 2', 'Bestseller'],
  },
  {
    id: 'best-match',
    badge: 'Best match',
    title: 'Shahi Royal Tasting Dastarkhwan',
    restaurantId: 'nawabs-dastarkhwan',
    restaurantName: "Nawab's Dastarkhwan",
    distanceKm: 1.4,
    deliveryFee: 25,
    totalPrice: 970,
    servesCount: 2,
    description: 'Exact match for authentic charcoal-cooked Kacchi Gosht paired with classic appetizers and meetha.',
    items: [
      { id: 'nb-1', name: 'Mutton Dum Biryani (Kacchi Gosht)', quantity: 1, price: 440, isVeg: false, spiceLevel: 'Hot' },
      { id: 'nb-3', name: 'Hyderabadi Tala Hua Gosht', quantity: 1, price: 380, isVeg: false, spiceLevel: 'Hot' },
      { id: 'nb-8', name: 'Shahi Double Ka Meetha', quantity: 1, price: 150, isVeg: true, spiceLevel: 'Not spicy' },
    ],
    tags: ['Highest Taste Match', 'Kacchi Gosht', 'Signature'],
  },
  {
    id: 'variety',
    badge: 'Variety',
    title: 'Veg Royal Dastarkhwan Platter',
    restaurantId: 'anarkali-veg',
    restaurantName: 'Anarkali Pure Veg & Thali',
    distanceKm: 2.1,
    deliveryFee: 0,
    totalPrice: 810,
    servesCount: 3,
    description: 'Rich vegetarian spread featuring handi biryani, smoky cottage cheese, and authentic apricot sweet.',
    items: [
      { id: 'av-1', name: 'Nizami Tarkari Dum Biryani', quantity: 1, price: 310, isVeg: true, spiceLevel: 'Medium' },
      { id: 'av-3', name: 'Authentic Bagara Baingan', quantity: 1, price: 240, isVeg: true, spiceLevel: 'Medium' },
      { id: 'av-5', name: 'Paneer Chandni Tikka', quantity: 1, price: 290, isVeg: true, spiceLevel: 'Not spicy' },
      { id: 'av-7', name: 'Qubani Ka Meetha with Fresh Malai', quantity: 1, price: 160, isVeg: true, spiceLevel: 'Not spicy' },
    ],
    tags: ['100% Pure Veg', 'Free Delivery', 'Mild & Balanced'],
  },
];
