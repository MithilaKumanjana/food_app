import os
import base64
import requests
from PIL import Image
import json
from datetime import datetime

class GPT4oFoodAnalyzer:
    def __init__(self, api_key):
        """
        Initialize the GPT-4o Food Analyzer
        
        Args:
            api_key (str): OpenAI API key
        """
        self.api_key = api_key
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        
        # Create output directory if it doesn't exist
        self.output_dir = "food_analysis_results"
        os.makedirs(self.output_dir, exist_ok=True)

    def crop_image(self, image_path, target_size=(768, 1024)):
        """
        Crop image to specified dimensions while maintaining aspect ratio
        
        Args:
            image_path (str): Path to the original image
            target_size (tuple): Target dimensions (width, height)
            
        Returns:
            str: Path to the cropped image
        """
        try:
            # Open the original image
            with Image.open(image_path) as img:
                print(f"📷 Original image size: {img.size}")
                
                # Calculate the aspect ratio
                original_width, original_height = img.size
                target_width, target_height = target_size
                
                # Calculate ratios
                width_ratio = target_width / original_width
                height_ratio = target_height / original_height
                
                # Use the smaller ratio to maintain aspect ratio
                ratio = min(width_ratio, height_ratio)
                
                # Calculate new dimensions
                new_width = int(original_width * ratio)
                new_height = int(original_height * ratio)
                
                # Resize the image
                resized_img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                
                # Create a new image with target dimensions and paste the resized image
                final_img = Image.new('RGB', target_size, (255, 255, 255))  # White background
                
                # Calculate position to center the image
                x_offset = (target_width - new_width) // 2
                y_offset = (target_height - new_height) // 2
                
                final_img.paste(resized_img, (x_offset, y_offset))
                
                # Save the cropped image
                base_name = os.path.splitext(os.path.basename(image_path))[0]
                cropped_path = os.path.join(self.output_dir, f"{base_name}_cropped_768x1024.jpg")
                final_img.save(cropped_path, "JPEG", quality=95)
                
                print(f"✅ Cropped image saved: {cropped_path}")
                return cropped_path
                
        except Exception as e:
            print(f"❌ Error cropping image: {e}")
            return None

    def encode_image(self, image_path):
        """Encode image to base64"""
        try:
            with open(image_path, "rb") as image_file:
                encoded = base64.b64encode(image_file.read()).decode('utf-8')
                print(f"✅ Image encoded successfully: {os.path.basename(image_path)}")
                return encoded
        except Exception as e:
            print(f"❌ Error encoding image {image_path}: {e}")
            return None

#     def create_food_analysis_prompt(self):
#         """Create a comprehensive prompt for food analysis"""
#         return """Please analyze this food image and provide:

# 1. FOOD IDENTIFICATION:
#    - List all the food items you can identify in the image
#    - Describe the cooking methods/preparation style
#    - Identify any garnishes or accompaniments

# 2. NUTRITIONAL ANALYSIS:
#    Please estimate the nutritional content for the total food shown in the image:
   
#    - Total Calories: [estimated amount]
#    - Protein: [grams and percentage]
#    - Carbohydrates: [grams and percentage] 
#    - Fat: [grams and percentage]
#    - Fiber: [grams]
#    - Sugar: [grams]
#    - Sodium: [milligrams]
   
# 3. ADDITIONAL NUTRITIONAL INFO:
#    - Key vitamins and minerals present
#    - Estimated portion size
#    - Health benefits of the dish
#    - Any dietary considerations (vegetarian, vegan, gluten-free, etc.)

# Please be as specific as possible based on what you can see in the image. If you're uncertain about exact amounts, please indicate that these are estimates."""
    def create_food_analysis_prompt(self):
        """Create a comprehensive prompt for food analysis using coin as scale reference"""
        return """Please analyze this food image and provide detailed nutritional information. 

IMPORTANT: There is a coin in this image with a diameter of 26mm (2.6cm). Please use this coin as a scale reference to accurately estimate the portion sizes and weights of all food items before calculating nutritional values.

1. SCALE ANALYSIS FIRST:
   - Locate the coin in the image (26mm diameter)
   - Use the coin to estimate the actual size/dimensions of each food item
   - Estimate the weight/volume of each food portion based on the coin scale
   - Show your scale calculations (e.g., "The rice portion appears to be approximately 3x the coin diameter, suggesting roughly X grams")

2. FOOD IDENTIFICATION:
   - List all the food items you can identify in the image
   - Describe the cooking methods/preparation style
   - Identify any garnishes or accompaniments
   - Estimate individual portion weights using the coin reference

3. DETAILED NUTRITIONAL ANALYSIS:
   Based on your scale-adjusted portion estimates, calculate the nutritional content for the total food shown:
   
   **MACRONUTRIENTS:**
   - Total Calories: [estimated amount with reasoning]
   - Protein: [grams and percentage of total calories]
   - Carbohydrates: [grams and percentage of total calories] 
   - Fat: [grams and percentage of total calories]
   - Fiber: [grams]
   - Sugar: [grams]
   - Sodium: [milligrams]
   
   **BREAKDOWN BY FOOD ITEM:**
   For each major food component, provide:
   - Estimated weight (using coin scale)
   - Individual calorie contribution
   - Key nutrients contributed

4. ADDITIONAL NUTRITIONAL INFO:
   - Key vitamins and minerals present
   - Estimated total meal weight
   - Health benefits of the overall dish
   - Any dietary considerations (vegetarian, vegan, gluten-free, etc.)
   - Meal balance assessment (protein/carb/fat ratios)

5. SCALE CONFIDENCE:
   - Rate your confidence in the size estimation (1-10)
   - Note any limitations in using the coin for scale reference
   - Mention if any food items are partially obscured or difficult to measure

Please be as specific as possible with your measurements and calculations. Show your reasoning for portion size estimates based on the 26mm coin reference. If you're uncertain about exact amounts, please indicate confidence levels and provide ranges."""

    def call_gpt4o_vision(self, image_path, image_type="original"):
        """
        Call GPT-4o Vision API for food analysis
        
        Args:
            image_path (str): Path to the image
            image_type (str): Type of image (original/cropped)
            
        Returns:
            str: API response text
        """
        print(f"\n🔍 Analyzing {image_type} image: {os.path.basename(image_path)}")
        
        # Encode image
        base64_image = self.encode_image(image_path)
        if not base64_image:
            return None
        
        # Create the payload
        payload = {
            "model": "gpt-4o",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": self.create_food_analysis_prompt()
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}",
                                "detail": "high"
                            }
                        }
                    ]
                }
            ],
            "max_tokens": 1000,
            "temperature": 0.3  # Lower temperature for more consistent nutritional estimates
        }
        
        try:
            print("📡 Making API call...")
            response = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers=self.headers,
                json=payload,
                timeout=60
            )
            
            if response.status_code == 200:
                result = response.json()
                analysis_text = result['choices'][0]['message']['content']
                print("✅ Analysis completed successfully!")
                return analysis_text
            else:
                print(f"❌ API Error {response.status_code}: {response.text}")
                return None
                
        except Exception as e:
            print(f"❌ Request error: {e}")
            return None

    def save_results(self, original_analysis, cropped_analysis, image_path):
        """Save analysis results to a text file"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_name = os.path.splitext(os.path.basename(image_path))[0]
        results_file = os.path.join(self.output_dir, f"{base_name}_analysis_{timestamp}.txt")
        
        try:
            with open(results_file, 'w', encoding='utf-8') as f:
                f.write("="*80 + "\n")
                f.write("GPT-4o FOOD ANALYSIS RESULTS\n")
                f.write("="*80 + "\n\n")
                f.write(f"Original Image: {os.path.basename(image_path)}\n")
                f.write(f"Analysis Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Model: GPT-4o\n\n")
                
                f.write("="*50 + "\n")
                f.write("ORIGINAL IMAGE ANALYSIS (Raw)\n")
                f.write("="*50 + "\n\n")
                if original_analysis:
                    f.write(original_analysis)
                else:
                    f.write("Analysis failed for original image.\n")
                
                f.write("\n\n" + "="*50 + "\n")
                f.write("CROPPED IMAGE ANALYSIS (768x1024)\n")
                f.write("="*50 + "\n\n")
                if cropped_analysis:
                    f.write(cropped_analysis)
                else:
                    f.write("Analysis failed for cropped image.\n")
                
                f.write("\n\n" + "="*80 + "\n")
                f.write("END OF ANALYSIS\n")
                f.write("="*80 + "\n")
            
            print(f"💾 Results saved to: {results_file}")
            return results_file
            
        except Exception as e:
            print(f"❌ Error saving results: {e}")
            return None

    def analyze_food_image(self, image_path):
        """
        Main function to analyze food image with both raw and cropped versions
        
        Args:
            image_path (str): Path to the food image
            
        Returns:
            dict: Analysis results
        """
        if not os.path.exists(image_path):
            print(f"❌ Image file not found: {image_path}")
            return None
        
        print("🍽️  Starting GPT-4o Food Analysis")
        print("="*60)
        print(f"📁 Input image: {image_path}")
        
        # Step 1: Analyze original image
        print("\n🔍 STEP 1: Analyzing original image...")
        original_analysis = self.call_gpt4o_vision(image_path, "original")
        
        # Step 2: Create cropped version
        print("\n✂️  STEP 2: Creating cropped version (768x1024)...")
        cropped_path = self.crop_image(image_path)
        
        cropped_analysis = None
        if cropped_path:
            # Step 3: Analyze cropped image
            print("\n🔍 STEP 3: Analyzing cropped image...")
            cropped_analysis = self.call_gpt4o_vision(cropped_path, "cropped")
        
        # Step 4: Display results
        print("\n📋 DISPLAYING RESULTS")
        print("="*60)
        
        if original_analysis:
            print("\n🖼️  ORIGINAL IMAGE ANALYSIS:")
            print("-" * 40)
            print(original_analysis)
        
        if cropped_analysis:
            print("\n✂️  CROPPED IMAGE ANALYSIS:")
            print("-" * 40)
            print(cropped_analysis)
        
        # Step 5: Save results
        results_file = self.save_results(original_analysis, cropped_analysis, image_path)
        
        # Return results
        results = {
            'original_image': image_path,
            'cropped_image': cropped_path,
            'original_analysis': original_analysis,
            'cropped_analysis': cropped_analysis,
            'results_file': results_file,
            'timestamp': datetime.now().isoformat()
        }
        
        print(f"\n✅ Analysis complete! Check '{self.output_dir}' folder for saved results.")
        return results

    def batch_analyze(self, image_folder):
        """Analyze multiple images in a folder"""
        if not os.path.exists(image_folder):
            print(f"❌ Folder not found: {image_folder}")
            return
        
        # Get all image files
        image_extensions = ('.jpg', '.jpeg', '.png', '.bmp', '.gif')
        image_files = [f for f in os.listdir(image_folder) 
                      if f.lower().endswith(image_extensions)]
        
        if not image_files:
            print(f"❌ No image files found in {image_folder}")
            return
        
        print(f"📂 Found {len(image_files)} images to analyze")
        
        results = []
        for i, image_file in enumerate(image_files, 1):
            print(f"\n{'='*60}")
            print(f"Processing image {i}/{len(image_files)}: {image_file}")
            print(f"{'='*60}")
            
            image_path = os.path.join(image_folder, image_file)
            result = self.analyze_food_image(image_path)
            if result:
                results.append(result)
        
        print(f"\n🎉 Batch analysis complete! Processed {len(results)} images successfully.")
        return results


def main():
    """Example usage of the GPT-4o Food Analyzer"""
    
    # Initialize analyzer with your API key
    API_KEY = "your-openai-api-key-here"  # Replace with your actual API key
    analyzer = GPT4oFoodAnalyzer(API_KEY)
    
    print("🚀 GPT-4o Food Image Analyzer")
    print("Make sure to set your OpenAI API key!")
    print("-" * 50)
    
    # Example usage options:
    
    # Option 1: Analyze a single image
    image_path = input("📁 Enter the path to your food image: ").strip()
    if image_path and os.path.exists(image_path):
        results = analyzer.analyze_food_image(image_path)
        if results:
            print(f"\n✅ Analysis saved to: {results['results_file']}")
    else:
        print("❌ Please provide a valid image path")
    
    # Option 2: Uncomment below for batch processing
    # folder_path = input("📂 Enter folder path for batch analysis: ").strip()
    # if folder_path and os.path.exists(folder_path):
    #     analyzer.batch_analyze(folder_path)


if __name__ == "__main__":
    # For VS Code usage:
    # 1. Replace API_KEY with your actual key
    # 2. Set your image path
    # 3. Run the script
    
    API_KEY = "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"  # <-- PUT YOUR API KEY HERE
    
    if API_KEY.startswith("sk-"):
        analyzer = GPT4oFoodAnalyzer(API_KEY)
        
        # Direct usage - just change the image path below:
        IMAGE_PATH = r"F:\idea8\food_analysis_results\WhatsApp Image 2025-06-29 at 16.56.12.jpeg"  # <-- PUT YOUR IMAGE PATH HERE
        
        if os.path.exists(IMAGE_PATH):
            print("🍽️  Analyzing your food image...")
            results = analyzer.analyze_food_image(IMAGE_PATH)
        else:
            print("❌ Image not found. Please update IMAGE_PATH variable.")
            # Fallback to interactive mode
            main()
    else:
        print("⚠️  Please set your OpenAI API key in the API_KEY variable!")
        main()