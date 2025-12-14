#!/usr/bin/env python3
"""
One-time script to detect and remove duplicate activities from Notion database.
This script will identify duplicates based on Date + Activity Type + Activity Name.
"""

import os
from collections import defaultdict

from dotenv import load_dotenv
from notion_client import Client


def get_all_activities_with_duplicates(client, database_id):
    """Fetch all activities and identify duplicates."""
    all_activities = []
    duplicates_map = defaultdict(list)
    has_more = True
    start_cursor = None

    print("Fetching all activities from Notion...")

    while has_more:
        query_params = {"database_id": database_id}
        if start_cursor:
            query_params["start_cursor"] = start_cursor

        response = client.databases.query(**query_params)

        for result in response["results"]:
            props = result["properties"]

            # Extract key information
            date = props.get("Date", {}).get("date", {}).get("start", "").split("T")[0]
            activity_type = props.get("Activity Type", {}).get("select", {}).get("name", "")
            activity_name = (
                props.get("Activity Name", {})
                .get("title", [{}])[0]
                .get("text", {})
                .get("content", "")
            )

            # Create unique identifier
            unique_key = f"{date}|{activity_type}|{activity_name}"

            # Store activity info
            activity_info = {
                "id": result["id"],
                "date": date,
                "activity_type": activity_type,
                "activity_name": activity_name,
                "unique_key": unique_key,
                "created_time": result.get("created_time", ""),
                "last_edited_time": result.get("last_edited_time", ""),
            }

            all_activities.append(activity_info)
            duplicates_map[unique_key].append(activity_info)

        has_more = response.get("has_more", False)
        start_cursor = response.get("next_cursor")

    print(f"Found {len(all_activities)} total activities")

    return all_activities, duplicates_map


def identify_duplicates(duplicates_map):
    """Identify which activities are duplicates."""
    duplicates = []
    duplicate_groups = 0
    total_duplicate_count = 0

    for unique_key, activities in duplicates_map.items():
        if len(activities) > 1:
            duplicate_groups += 1
            total_duplicate_count += len(activities)

            # Sort by created_time to keep the oldest one (first created)
            activities.sort(key=lambda x: x["created_time"])

            # Mark all but the first one as duplicates to remove
            duplicates_to_remove = activities[1:]  # Keep the first, remove the rest

            duplicates.extend(duplicates_to_remove)

            print(f"\nDuplicate group {duplicate_groups}:")
            print(f"  Key: {unique_key}")
            print(f"  Found {len(activities)} copies")
            print(f"  Keeping: {activities[0]['id']} (created: {activities[0]['created_time']})")
            for dup in duplicates_to_remove:
                print(f"  Will remove: {dup['id']} (created: {dup['created_time']})")

    print("\nSummary:")
    print(f"  Total duplicate groups: {duplicate_groups}")
    print(f"  Total activities in duplicate groups: {total_duplicate_count}")
    print(f"  Activities to be removed: {len(duplicates)}")

    return duplicates


def remove_duplicates(client, duplicates):
    """Remove duplicate activities from Notion."""
    if not duplicates:
        print("No duplicates to remove!")
        return

    print(f"\nStarting removal of {len(duplicates)} duplicate activities...")

    removed_count = 0
    for i, duplicate in enumerate(duplicates, 1):
        try:
            # Delete the page
            client.pages.update(
                page_id=duplicate["id"], archived=True  # Archive instead of hard delete
            )
            removed_count += 1
            print(
                f"  [{i}/{len(duplicates)}] Archived: {duplicate['activity_name']} on {duplicate['date']}"
            )

        except Exception as e:
            print(f"  [{i}/{len(duplicates)}] Error removing {duplicate['id']}: {e}")

    print(f"\nCompleted! Successfully archived {removed_count}/{len(duplicates)} duplicates")


def main():
    load_dotenv()

    # Get environment variables
    notion_token = os.getenv("NOTION_TOKEN")
    database_id = os.getenv("NOTION_DB_ID")

    if not notion_token or not database_id:
        print("Error: Missing NOTION_TOKEN or NOTION_DB_ID environment variables")
        return

    # Initialize Notion client
    client = Client(auth=notion_token)

    print("=== Notion Activities Duplicate Cleanup ===")
    print("This script will identify and remove duplicate activities.")
    print("Duplicates are identified by: Date + Activity Type + Activity Name")
    print("The oldest entry (by creation time) will be kept.\n")

    # Get confirmation
    confirm = input("Do you want to proceed? (yes/no): ").strip().lower()
    if confirm not in ["yes", "y"]:
        print("Cleanup cancelled.")
        return

    try:
        # Step 1: Fetch all activities and identify duplicates
        all_activities, duplicates_map = get_all_activities_with_duplicates(client, database_id)

        # Step 2: Identify which ones to remove
        duplicates_to_remove = identify_duplicates(duplicates_map)

        if not duplicates_to_remove:
            print("\n✅ No duplicates found! Your database is clean.")
            return

        # Step 3: Ask for final confirmation
        print(f"\nFound {len(duplicates_to_remove)} duplicate activities to remove.")
        final_confirm = input("Proceed with removal? (yes/no): ").strip().lower()

        if final_confirm not in ["yes", "y"]:
            print("Cleanup cancelled.")
            return

        # Step 4: Remove duplicates
        remove_duplicates(client, duplicates_to_remove)

        print("\n✅ Duplicate cleanup completed successfully!")
        print("Note: Duplicates were archived (not permanently deleted).")

    except Exception as e:
        print(f"\n❌ Error during cleanup: {e}")
        print("Please check your Notion token and database ID.")


if __name__ == "__main__":
    main()
