// We are impersonating a mobile client, so these headers are expected by the AH mobile api
const HEADERS = {
    Host: 'api.ah.nl',
    'x-dynatrace': 'MT_3_4_772337796_1_fae7f753-3422-4a18-83c1-b8e8d21caace_0_1589_109',
    'x-application': 'AHWEBSHOP',
    'x-flow-id': 'appie',
    'user-agent': 'Appie/8.8.2 Model/phone Android/7.0-API24',
    'content-type': 'application/json; charset=UTF-8',
};

// Function to convert the first letter of a string to toUpperCase
// Used for nice formatting
function FirstUpper(s) {
    let c = s.charAt(0);
    return c.toUpperCase() + s.slice(1);
}

// AH Bonus starts on monday
function getPreviousMonday() {
    const today = new Date();
    const day = today.getDay(); // 0 = Sunday, 1 = Monday, ..., 6 = Saturday

    const diff = day === 0 ? 6 : day - 1;
    const prevMonday = new Date(today);
    prevMonday.setDate(today.getDate() - diff);

    const year = prevMonday.getFullYear();
    const month = String(prevMonday.getMonth() + 1).padStart(2, '0');
    const date = String(prevMonday.getDate()).padStart(2, '0');

    return `${year}-${month}-${date}`;
}

export class AHConnector {
    constructor() {
        this._accessToken = null;
    }
    // Since this is a async function, it can´t be in the constructor
    async init() {
        this._accessToken = await this.getAnonymousAccessToken();
    }
    // AH Api stuff, a random user id token is needed
    async getAnonymousAccessToken() {
        const response = await fetch('https://api.ah.nl/mobile-auth/v1/auth/token/anonymous', {
            method: 'POST',
            headers: HEADERS,
            body: JSON.stringify({
                clientId: 'appie',
            }),
        });

        if (!response.ok) {
            throw new Error(`Auth failed: ${response.status}`);
        }

        return response.json();
    }
    // Function to search a product
    async searchProducts({ query = '', page = 0, size = 750, sort = 'RELEVANCE' } = {}) {
        const url = new URL('https://api.ah.nl/mobile-services/product/search/v2');

        url.searchParams.set('sortOn', sort);
        url.searchParams.set('page', page);
        url.searchParams.set('size', size);
        url.searchParams.set('query', query);

        const response = await fetch(url.toString(), {
            method: 'GET',
            headers: {
                ...HEADERS,
                Authorization: `Bearer ${this._accessToken.access_token}`,
            },
        });

        if (!response.ok) {
            throw new Error(`HTTP error: ${response.status}`);
        }

        return response.json();
    }
    // Get details of the product
    async getProductDetails(product) {
        const productId = typeof product === 'object' ? product.webshopId : product;

        const response = await fetch(`https://api.ah.nl/mobile-services/product/detail/v4/fir/${productId}`, {
            headers: {
                ...HEADERS,
                Authorization: `Bearer ${this._accessToken.access_token}`,
            },
        });

        if (!response.ok) {
            throw new Error(`Product details failed: ${response.status}`);
        }

        return response.json();
    }
    // Combines the product details and searchproduct with a nice formatted result
    // Also return the cheapeast option
    async getProduct(query = 'Melk', size = '50') {
        const res = await this.searchProducts({
            query: query,
            page: 0,
            size: size,
            sort: 'RELEVANCE',
        });
        var index = 0;
        var indexSelected = 0;
        var price = 0;
        for await (var product of res.products) {
            if (product.priceBeforeBonus < price || price == 0) {
                price = product.priceBeforeBonus;
                indexSelected = index;
            }
            index += 1;
        }
        const pr = res.products[indexSelected];
        var p = await this.getProductDetails(res.products[indexSelected]);
        const excludedIntolerances = Object.entries(p.properties)
            .filter(([key]) => key.startsWith('sp_exclude_in'))
            .map(([_, value]) => FirstUpper(value[0].replace('Geen ', '')));

        const jsonReturn = JSON.stringify({
            name: pr.title,
            price: pr.currentPrice ?? p.productCard.priceBeforeBonus,
            size: p.productCard.salesUnitSize,
            alcohol: p.productCard.nix18,
            nutriscore: p.properties.nutriscore,
            allergenes: excludedIntolerances,
        });

        return jsonReturn;
    }
    // Return a list of all the products in the bonus
    async GetBonusProducts() {
        const categories = [
            //'Groente, aardappelen',
            //'Fruit, verse sappen',
            'Vlees',
            'Vis',
            //'Zuivel, eieren',
            //'Diepvries',
            // 'Pasta, rijst, wereldkeuken',
        ];
        const responses = [];
        const url = new URL('https://api.ah.nl/mobile-services/bonuspage/v2/section');
        url.searchParams.set('date', getPreviousMonday());
        url.searchParams.set('promotionType', 'NATIONAL');
        for (var category of categories) {
            console.log(`Fetching category: ${category}`);
            const url1 = url;
            url1.searchParams.set('category', category);
            const response = await fetch(url1, {
                headers: {
                    ...HEADERS,
                    Authorization: `Bearer ${this._accessToken.access_token}`,
                },
            });

            if (!response.ok) {
                throw new Error(`Category failed: ${category}`);
            }
            var l = await response.json();
            for (var p of l.bonusGroupOrProducts) {
                if (p.bonusGroup != undefined) {
                    if (p.bonusGroup.segmentId != undefined) {
                        if (p.bonusGroup.storeOnlyPromotion) continue;
                        responses.push(await this.getGroupProducts(p.bonusGroup.segmentId));
                    }
                } else if (p.product != undefined) {
                    if (p.product.id != undefined) {
                        responses.push(await this.getGroupProducts(p.product.id));
                    }
                }
            }
        }
        console.log(responses);
        return responses;
    }
    // Helper function to get all get all the products from one bonus category
    async getGroupProducts(id) {
        const url = new URL('https://api.ah.nl/mobile-services/bonuspage/v1/segment');
        url.searchParams.set('date', getPreviousMonday());
        url.searchParams.set('segmentId', id);

        var response = await fetch(url, {
            headers: {
                ...HEADERS,
                Authorization: `Bearer ${this._accessToken.access_token}`,
            },
        });
        if (!response.ok) {
            throw new Error(`Segment failed: ${id}`);
        }
        return this.getOfferProducts(await response.json());
    }
    async getOfferProducts(response) {
        const responses = [];
        for (var product of response.products) {
            const excludedIntolerances = Object.entries(product.properties)
                .filter(([key]) => key.startsWith('sp_exclude_in'))
                .map(([_, value]) => FirstUpper(value[0].replace('Geen ', '')));
            var price = product.currentPrice;
            switch (product.discountLabels[0].code) {
                case 'DISCOUNT_ONE_HALF_PRICE':
                    price = product.priceBeforeBonus * 0.75;
                    break;
                case 'DISCOUNT_FIXED_PRICE':
                    // Not needed
                    break;
                case 'DISCOUNT_X_PLUS_Y_FREE':
                    // x = count, y = freeCount
                    price =
                        (product.priceBeforeBonus / (product.discountLabels[0].count + product.discountLabels[0].freeCount)) *
                        product.discountLabels[0].count;
                    break;
                case 'DISCOUNT_AMOUNT':
                    // Not needed
                    break;
                case 'DISCOUNT_PERCENTAGE':
                    // Not needed
                    break;
                case 'DISCOUNT_X_FOR_Y':
                    // count, price
                    price = product.discountLabels[0].price / product.discountLabels[0].count;
                    break;
                case 'DISCOUNT_WEIGHT':
                    // count, price, unit
                    price = product.discountLabels[0].price;
                    break;
                case 'DISCOUNT_TIERED_PRICE':
                    // count, price, unit
                    price = product.discountLabels[0].price;
                    break;
                case 'DISCOUNT_BONUS':
                    // Not needed
                    break;
                default:
                //console.log(product.discountLabels);
            }
            const jsonReturn = JSON.stringify({
                name: product.title,
                bonusMechanism: product.bonusMechanism,
                price: price,
                size: product.salesUnitSize,
                alcohol: product.nix18,
                nutriscore: product.nutriscore,
                allergenes: excludedIntolerances,
            });
            responses.push(jsonReturn);
        }
        return responses;
    }
}
